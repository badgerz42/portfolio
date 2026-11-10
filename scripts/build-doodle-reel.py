#!/usr/bin/env python3
"""Hand-drawn doodle montage (?reel=doodle), after the adidas 'There Will Be Haters' spot.

Longer shots of the recent work with boiling, marker-style doodles and emoticons that track each
subject (via the SAM3 mattes in .collage-cache/), a wobbling hand-drawn outline around the
subject, short psychedelic kaleidoscope bursts (~0.3 s) on some cuts, and the collage reel's
motion vocabulary on the others (whip, zoom punch, 3D spin, slam, drop, B&W/duotone flips, a slam-in split).

Inputs: .collage-cache/src/<name>.mp4 and .collage-cache/matte/<name>/ (see README).
Outputs: public/assets/generated/reel/reel-doodle-{720,480}.mp4, -poster.jpg, .json
"""
import json
import math
import multiprocessing
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / 'public'
CACHE = ROOT / '.collage-cache'
OUT = PUB / 'assets/generated/reel'
W, H, FPS = 1280, 720, 24
SS = 2  # doodles are drawn at 2x and downsampled for smooth marker edges

ACID = (166, 255, 0)
PINK = (255, 40, 160)
WHITE = (246, 246, 240)
RED = (255, 52, 60)
ART = 'assets/artstation'
FUGI = 'assets/projects/fugi-visualizer'
RNG = np.random.default_rng(11)


def _has_nvenc():
    probe = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    return 'h264_nvenc' in probe


# Encode on the GPU (NVENC) when available; x264 on the CPU otherwise.
if _has_nvenc():
    ENCODER = ['-c:v', 'h264_nvenc', '-preset', 'p6', '-tune', 'hq', '-rc', 'vbr', '-cq', '30', '-b:v', '0']
    ENCODER_SMALL = ['-c:v', 'h264_nvenc', '-preset', 'p6', '-tune', 'hq', '-rc', 'vbr', '-cq', '31', '-b:v', '0']
else:
    ENCODER = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '24']
    ENCODER_SMALL = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '26']
FG_SCALE = 0.6  # foreground doodles: accents, not stickers


def _collage():
    """The collage reel's motion vocabulary (transitions, splits, grades) so both edits move alike."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('collage', ROOT / 'scripts' / 'build-collage-reel.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLLAGE = _collage()


# ---------------------------------------------------------------- sources

def cover(img):
    s = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((l, t, l + W, t + H))


def load_clip(name, start, frames, zoom=1.0):
    """Frames + mattes of a cached clip. `zoom` > 1 crops in on the subject (fixed crop centred on its
    average position), so small subjects fill the frame and the doodles have room."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(CACHE / 'src' / f'{name}.mp4'), '-frames:v', str(frames),
                          '-vf', f'scale={W}:{H},format=rgb24', '-f', 'rawvideo', '-'], check=True, capture_output=True).stdout
    arr = list(np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3))
    first = round(start * FPS)
    files = sorted((CACHE / 'matte' / name).glob('*.png'))[first:first + len(arr)]
    mattes = [np.asarray(Image.open(f).convert('L').resize((W, H))) for f in files]
    if zoom > 1:
        centres = []
        for m in mattes:
            ys, xs = np.where(m[::4, ::4] > 100)
            if len(xs):
                centres.append((xs.mean() * 4, ys.mean() * 4))
        cx, cy = np.mean(centres, 0) if centres else (W / 2, H / 2)
        cw, ch = W / zoom, H / zoom
        left, top = min(max(cx - cw / 2, 0), W - cw), min(max(cy - ch * 0.55, 0), H - ch)
        box = (left, top, left + cw, top + ch)
        arr = [np.asarray(Image.fromarray(a).resize((W, H), Image.BICUBIC, box=box)) for a in arr]
        mattes = [np.asarray(Image.fromarray(m).resize((W, H), Image.BILINEAR, box=box)) for m in mattes]
    return arr, mattes


def load_still(path, name, frames, push=0.06):
    """A still with a slow push-in; the matte is pushed identically."""
    img, matte = cover(Image.open(PUB / path).convert('RGB')), cover(Image.open(CACHE / 'matte' / name / '0000.png').convert('L'))
    out_f, out_m = [], []
    for i in range(frames):
        z = 1 + push * i / max(1, frames - 1)
        cw, ch = W / z, H / z
        box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
        out_f.append(np.asarray(img.resize((W, H), Image.BICUBIC, box=box)))
        out_m.append(np.asarray(matte.resize((W, H), Image.BILINEAR, box=box)))
    return out_f, out_m


def smooth_boxes(mattes, window=5):
    """Per-frame subject bbox (x0, y0, x1, y1), smoothed so doodles don't jitter with the matte."""
    boxes = []
    for m in mattes:
        ys, xs = np.where(m[::4, ::4] > 100)
        boxes.append(np.array([xs.min() * 4, ys.min() * 4, xs.max() * 4, ys.max() * 4], float) if len(xs) else None)
    known = [b for b in boxes if b is not None]
    fallback = np.mean(known, 0) if known else np.array([W * 0.3, H * 0.2, W * 0.7, H * 0.9])
    boxes = np.array([b if b is not None else fallback for b in boxes])
    out = np.empty_like(boxes)
    for i in range(len(boxes)):
        out[i] = boxes[max(0, i - window):i + window + 1].mean(0)
    return out


# ---------------------------------------------------------------- doodle shapes (unit coords, y down)

def circle_pts(n=28, rx=1.0, ry=1.0, cx=0.0, cy=0.0, start=0.0, sweep=2 * math.pi):
    t = np.linspace(start, start + sweep, n)
    return np.stack([cx + rx * np.cos(t), cy + ry * np.sin(t)], 1)


def shape(kind):
    """List of (points, closed, filled) in roughly [-1, 1]."""
    if kind == 'sparkle':
        return [(np.array([[0, -1], [0, 1]]), False, False), (np.array([[-1, 0], [1, 0]]), False, False),
                (np.array([[-0.62, -0.62], [0.62, 0.62]]), False, False), (np.array([[-0.62, 0.62], [0.62, -0.62]]), False, False)]
    if kind == 'star':
        pts = [(math.sin(a) * (1 if k % 2 == 0 else 0.45), -math.cos(a) * (1 if k % 2 == 0 else 0.45))
               for k, a in enumerate(np.linspace(0, 2 * math.pi, 11)[:-1])]
        return [(np.array(pts), True, True)]
    if kind == 'heart':
        t = np.linspace(0, 2 * math.pi, 40)
        x = 16 * np.sin(t) ** 3
        y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
        return [(np.stack([x, y], 1) / 17, True, True)]
    if kind == 'spiral':
        t = np.linspace(0, 5.5 * math.pi, 70)
        r = t / (5.5 * math.pi)
        return [(np.stack([r * np.cos(t), r * np.sin(t)], 1), False, False)]
    if kind == 'bolt':
        return [(np.array([[0.25, -1], [-0.35, 0.05], [0.15, 0.05], [-0.25, 1], [0.45, -0.2], [-0.05, -0.2], [0.35, -1]]), True, True)]
    if kind == 'note':
        return [(circle_pts(16, 0.32, 0.24, -0.25, 0.7), True, True), (np.array([[0.07, 0.7], [0.07, -0.9], [0.55, -0.55]]), False, False)]
    if kind == 'notes':
        return [(circle_pts(14, 0.24, 0.18, -0.6, 0.72), True, True), (circle_pts(14, 0.24, 0.18, 0.45, 0.55), True, True),
                (np.array([[-0.36, 0.72], [-0.36, -0.75], [0.69, -0.95], [0.69, 0.55]]), False, False)]
    if kind == 'drops':
        drop = lambda cx, cy, s: circle_pts(18, 0.3 * s, 0.34 * s, cx, cy + 0.1 * s, math.radians(-30), math.radians(240)).tolist() + [[cx, cy - 0.55 * s]]
        return [(np.array(drop(-0.45, 0.0, 1.0)), True, True), (np.array(drop(0.35, -0.35, 0.75)), True, True)]
    if kind == 'motion':
        return [(np.array([[-1, y], [0.6 - abs(y) * 0.4, y]]), False, False) for y in (-0.55, 0.0, 0.55)]
    if kind == 'bang':
        return [(np.array([[-0.3, -1], [-0.22, 0.35]]), False, False), (circle_pts(10, 0.09, 0.09, -0.2, 0.75), True, True),
                (np.array([[0.3, -1], [0.22, 0.35]]), False, False), (circle_pts(10, 0.09, 0.09, 0.2, 0.75), True, True)]
    if kind == 'smiley':
        return [(circle_pts(30), True, False), (circle_pts(8, 0.1, 0.13, -0.35, -0.25), True, True),
                (circle_pts(8, 0.1, 0.13, 0.35, -0.25), True, True), (circle_pts(16, 0.55, 0.45, 0, 0.05, math.radians(20), math.radians(140)), False, False)]
    if kind == 'skull':
        head = circle_pts(26, 0.85, 0.75, 0, -0.2, math.radians(140), math.radians(260))
        jaw = np.array([[0.55, 0.45], [0.5, 0.9], [-0.5, 0.9], [-0.55, 0.45]])
        return [(np.vstack([head, jaw]), True, False), (circle_pts(12, 0.22, 0.25, -0.33, -0.15), True, True),
                (circle_pts(12, 0.22, 0.25, 0.33, -0.15), True, True)] + [(np.array([[x, 0.62], [x, 0.9]]), False, False) for x in (-0.25, 0, 0.25)]
    if kind == 'heart_eyes':
        eye = lambda cx: shape('heart')[0][0] * 0.28 + [cx, -0.22]
        return [(circle_pts(30), True, False), (eye(-0.36), True, True), (eye(0.36), True, True),
                (circle_pts(16, 0.5, 0.4, 0, 0.12, math.radians(15), math.radians(150)), False, False)]
    if kind == 'crown':
        return [(np.array([[-1, 0.6], [-1, -0.5], [-0.5, 0.05], [0, -0.8], [0.5, 0.05], [1, -0.5], [1, 0.6]]), True, False)]
    if kind == 'halo':
        return [(circle_pts(34, 1.0, 0.28), True, False)]
    if kind == 'eyes':
        return [(circle_pts(18, 0.42, 0.26, -0.5, 0), True, False), (circle_pts(10, 0.12, 0.12, -0.45, 0.02), True, True),
                (circle_pts(18, 0.42, 0.26, 0.5, 0), True, False), (circle_pts(10, 0.12, 0.12, 0.55, 0.02), True, True)]
    if kind == 'rays':
        return [(np.array([[math.cos(a) * 0.55, math.sin(a) * 0.55], [math.cos(a), math.sin(a)]]), False, False)
                for a in np.linspace(0, 2 * math.pi, 11)[:-1]]
    if kind == 'arrow':
        return [(np.array([[0, 1], [0, -1]]), False, False), (np.array([[-0.45, -0.5], [0, -1], [0.45, -0.5]]), False, False)]
    if kind == 'zzz':
        z = lambda cx, cy, s: np.array([[cx - s, cy - s], [cx + s, cy - s], [cx - s, cy + s], [cx + s, cy + s]])
        return [(z(-0.5, 0.5, 0.3), False, False), (z(0.05, -0.05, 0.24), False, False), (z(0.5, -0.55, 0.18), False, False)]
    if kind == 'squiggle':
        t = np.linspace(-1, 1, 40)
        return [(np.stack([t, 0.35 * np.sin(t * 9)], 1), False, False)]
    if kind == 'fire':
        return [(np.array([[0, -1], [0.45, -0.3], [0.3, -0.45], [0.7, 0.2], [0.55, 0.85], [0, 1], [-0.55, 0.85], [-0.7, 0.2],
                           [-0.3, -0.2], [-0.2, 0.1], [-0.05, -0.4]]), True, True)]
    # Background sketch motifs: line art, not emoticons.
    if kind == 'ghost':
        top = circle_pts(20, 0.62, 0.62, 0, -0.25, math.pi, math.pi)
        hem = [[0.62, 0.75], [0.35, 0.95], [0.12, 0.72], [-0.12, 0.95], [-0.38, 0.72], [-0.62, 0.95]]
        return [(np.vstack([top, [[0.62, -0.25]], hem, [[-0.62, -0.25]]]), True, False),
                (circle_pts(10, 0.1, 0.16, -0.22, -0.3), True, True), (circle_pts(10, 0.1, 0.16, 0.22, -0.3), True, True),
                (circle_pts(10, 0.14, 0.08, 0, 0.05), True, False)]
    if kind == 'eyeblob':
        t = np.linspace(0, 2 * math.pi, 30)
        r = 0.8 + 0.12 * np.sin(t * 5) + 0.06 * np.cos(t * 3)
        body = np.stack([r * np.cos(t), 0.75 * r * np.sin(t)], 1)
        eyes = [(circle_pts(10, 0.16, 0.16, x, y), True, False) for x, y in ((-0.35, -0.15), (0.2, -0.3), (0.4, 0.15))]
        pupils = [(circle_pts(6, 0.06, 0.06, x, y), True, True) for x, y in ((-0.33, -0.12), (0.22, -0.27), (0.42, 0.18))]
        return [(body, True, False)] + eyes + pupils
    if kind == 'peeker':
        grin = np.array([[-0.7, 0.35], [-0.45, 0.6], [-0.25, 0.4], [0, 0.65], [0.25, 0.4], [0.45, 0.6], [0.7, 0.35]])
        return [(circle_pts(14, 0.3, 0.3, -0.42, -0.2), True, False), (circle_pts(7, 0.09, 0.09, -0.36, -0.14), True, True),
                (circle_pts(14, 0.3, 0.3, 0.42, -0.2), True, False), (circle_pts(7, 0.09, 0.09, 0.48, -0.14), True, True),
                (grin, False, False)]
    if kind == 'rabbit':
        head = circle_pts(24, 0.5, 0.42, 0, 0.35)
        ear_l = np.array([[-0.28, 0.02], [-0.5, -0.95], [-0.12, -0.2]])
        ear_r = np.array([[0.28, 0.02], [0.5, -0.95], [0.12, -0.2]])
        return [(head, True, False), (ear_l, False, False), (ear_r, False, False),
                (np.array([[-0.25, 0.3], [-0.1, 0.3]]), False, False), (np.array([[0.1, 0.3], [0.25, 0.3]]), False, False),
                (shape('heart')[0][0] * 0.08 + [0, 0.5], True, True)]
    raise KeyError(kind)


def resample(pts, closed, step=0.08):
    if closed:
        pts = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    length = np.concatenate([[0], np.cumsum(seg)])
    if length[-1] == 0:
        return pts
    t = np.linspace(0, length[-1], max(2, int(length[-1] / step) + 1))
    return np.stack([np.interp(t, length, pts[:, 0]), np.interp(t, length, pts[:, 1])], 1)


def wobble(pts, seed, amount):
    """Hand-drawn wobble: smooth low-frequency noise along the line, re-rolled every boil step."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, amount, pts.shape)
    taps = min(5, len(pts))
    kernel = np.ones(taps) / taps
    noise = np.stack([np.convolve(noise[:, k], kernel, mode='same')[:len(pts)] for k in range(2)], 1) * 2.2
    return pts + noise


def back_out(t, overshoot=2.2):
    t = min(max(t, 0.0), 1.0) - 1
    return 1 + t * t * ((overshoot + 1) * t + overshoot)


class Doodle:
    def __init__(self, kind, u, v, size, colour, appear=0, anchor='bbox', rot=0.0, spin=0.0, drift=(0.0, 0.0), width=1.0, scale=FG_SCALE):
        self.kind, self.u, self.v, self.size, self.colour = kind, u, v, size, colour
        self.appear, self.anchor, self.rot, self.spin, self.drift, self.width = appear, anchor, rot, spin, np.array(drift), width
        self.parts = [(resample(np.asarray(p, float), c), c, f) for p, c, f in shape(kind)]
        self.seed = int(RNG.integers(1 << 30))
        self.scale_mult = scale

    def draw(self, draw, i, box):
        age = i - self.appear
        if age < 0:
            return
        pop = back_out(age / 4)
        if self.anchor in ('bbox', 'follow'):
            # 'follow' tracks the subject but sizes to the frame, for small subjects.
            x0, y0, x1, y1 = box
            cx, cy = x0 + self.u * (x1 - x0), y0 + self.v * (y1 - y0)
            scale = self.size * (H if self.anchor == 'follow' else (y1 - y0))
        else:
            cx, cy, scale = self.u * W, self.v * H, self.size * H
        scale *= self.scale_mult
        cx, cy = cx + self.drift[0] * age, cy + self.drift[1] * age
        boil = age // 2  # redrawn on twos, like hand animation
        wiggle = 4 * math.sin(boil * 1.7 + self.seed % 7)
        a = math.radians(self.rot + self.spin * age + wiggle)
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        line = max(1.6, scale * 0.06) * self.width * SS
        for k, (pts, closed, filled) in enumerate(self.parts):
            p = wobble(pts, self.seed + boil * 101 + k, 0.018) @ rot.T * scale * pop
            p = [(float((cx + x) * SS), float((cy + y) * SS)) for x, y in p]
            if filled and len(p) > 2:
                draw.polygon(p, fill=self.colour + (255,))
            draw.line(p, fill=self.colour + (255,), width=int(line), joint='curve')
            # Second, thinner pass slightly off the first: the double-stroke marker look.
            p2 = wobble(pts, self.seed + boil * 101 + k + 50, 0.022) @ rot.T * scale * pop
            p2 = [(float((cx + x) * SS), float((cy + y) * SS)) for x, y in p2]
            draw.line(p2, fill=self.colour + (200,), width=max(1, int(line * 0.45)), joint='curve')
            for x, y in (p[0], p[-1]):
                r = line / 2
                draw.ellipse((x - r, y - r, x + r, y + r), fill=self.colour + (255,))


def outline(matte, i, colour, width=3):
    """Boiling hand-drawn outline hugging the subject: a ring around the matte, displaced by noise on twos."""
    small = Image.fromarray(matte).resize((W // 2, H // 2), Image.BILINEAR).point(lambda v: 255 if v > 110 else 0)
    outer = small.filter(ImageFilter.MaxFilter(2 * width + 3))
    inner = small.filter(ImageFilter.MaxFilter(3))
    ring = np.asarray(outer, np.float32) - np.asarray(inner, np.float32)
    rng = np.random.default_rng(900 + i // 2)
    grid = rng.normal(0, 2.4, (2, 6, 10)).astype(np.float32)
    dx = np.asarray(Image.fromarray(grid[0]).resize((W // 2, H // 2), Image.BICUBIC))
    dy = np.asarray(Image.fromarray(grid[1]).resize((W // 2, H // 2), Image.BICUBIC))
    yy, xx = np.mgrid[0:H // 2, 0:W // 2]
    sx = np.clip(xx + dx, 0, W // 2 - 1).astype(np.int32)
    sy = np.clip(yy + dy, 0, H // 2 - 1).astype(np.int32)
    ring = ring[sy, sx]
    alpha = Image.fromarray(np.clip(ring, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    layer = Image.new('RGBA', (W, H), colour + (0,))
    layer.putalpha(alpha)
    return layer


# ---------------------------------------------------------------- doodles painted into the scene

def _blur_up(arr, factor=8, radius=2.0):
    """Cheap large blur: downsample, blur, upsample (for lighting)."""
    small = Image.fromarray(arr).resize((W // factor, H // factor), Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(small.resize((W, H), Image.BILINEAR), np.float32)


def _bilinear(field, x, y):
    """Sample an (h, w, ...) field at float pixel coords given in full-res units of a W x H frame."""
    h, w = field.shape[:2]
    fx = np.clip(x * (w / W), 0, w - 1.001)
    fy = np.clip(y * (h / H), 0, h - 1.001)
    x0, y0 = fx.astype(np.int32), fy.astype(np.int32)
    ax, ay = fx - x0, fy - y0
    if field.ndim == 3:
        ax, ay = ax[..., None], ay[..., None]
    top = field[y0, x0] * (1 - ax) + field[y0, x0 + 1] * ax
    bottom = field[y0 + 1, x0] * (1 - ax) + field[y0 + 1, x0 + 1] * ax
    return top * (1 - ay) + bottom * ay


class ScenePaint:
    """Doodles painted onto the background: placed on real surfaces (depth), carried by the scene's
    optical flow (or the still's push), foreshortened on slanted surfaces, occluded per pixel by anything
    nearer, shaded by the local light and drawn on stroke by stroke before they boil."""

    def __init__(self, colours, kinds=(), seed=0, count=14, size=60.0, track='dense', mode='motifs', opacity=0.85, dim=0.0):
        """mode: 'motifs' (sketched creatures/patterns on surfaces), 'hatch' (hatching over the background),
        'radial' (comic focus lines + signal arcs around the subject), 'staff' (flowing music staves).
        dim: darken the background under the sketch so the subject stands out."""
        self.colours, self.kinds, self.seed, self.count, self.size, self.track = colours, list(kinds), seed, count, size, track
        self.mode, self.opacity, self.dim = mode, opacity, dim

    def prepare(self, spec, frames, mattes, frames_n):
        self.n = frames_n
        name = spec[1] if spec[0] == 'clip' else spec[2]
        if spec[0] == 'clip':
            first = round(spec[2] * FPS)
            files = sorted((CACHE / 'depth' / name).glob('*.png'))[first:first + frames_n]
            self.depths = [np.asarray(Image.open(f).convert('L').resize((W, H), Image.BILINEAR), np.float32) / 255 for f in files]
            self.flow = np.load(CACHE / 'flow' / f'{name}.npy').astype(np.float32)[first:first + frames_n]
            self.push = None
        else:
            depth = cover(Image.open(ROOT / '.depth-cache' / name / '0000.png').convert('L'))
            self.depths, self.push = [], 0.06
            for i in range(frames_n):
                z = 1 + self.push * i / max(1, frames_n - 1)
                cw, ch = W / z, H / z
                box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
                self.depths.append(np.asarray(depth.resize((W, H), Image.BILINEAR, box=box), np.float32) / 255)
            self.flow = None
        while len(self.depths) < frames_n:
            self.depths.append(self.depths[-1])
        # Normalise depth for the whole shot (inverse depth: 1 = nearest).
        lo, hi = np.percentile(self.depths[0], (1, 99))
        self.depths = [np.clip((d - lo) / max(hi - lo, 1e-3), 0, 1) for d in self.depths]
        getattr(self, f'_place_{self.mode}')(frames[0], mattes[0])

    def _item(self, parts, anchor, size, appear, width=None, wobble=None, depth=None, colour=None):
        return {'parts': parts, 'anchor': np.asarray(anchor, float), 'size': size, 'appear': appear,
                'colour': colour or self.colours[0], 'seed': int(np.random.default_rng(len(self.items) + self.seed).integers(1 << 30)),
                'width': width or max(1.2, size * 0.045), 'wobble': size * 0.012 if wobble is None else wobble, 'depth': depth}

    def _backdrop(self, matte):
        depth = self.depths[0]
        subject_depth = float(np.median(depth[matte > 128])) if (matte > 128).any() else 1.0
        near = np.asarray(Image.fromarray(matte).filter(ImageFilter.MaxFilter(31)), np.float32) / 255
        return (depth < subject_depth - 0.03) & (near < 0.05), subject_depth

    def _place_hatch(self, frame, matte):
        """Hand-drawn hatching over the background; darker areas get a second, crossing pass."""
        self.items = []
        back, subject_depth = self._backdrop(matte)
        dark = _blur_up(frame.mean(-1).astype(np.uint8)) / 255 < 0.33
        rng = np.random.default_rng(self.seed)
        for angle, spacing, region in ((38, self.size, back), (-52, self.size * 1.35, back & dark)):
            a = math.radians(angle)
            direction, normal = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
            reach = math.hypot(W, H)
            for offset in np.arange(-reach / 2, reach / 2, spacing):
                origin = np.array([W / 2, H / 2]) + normal * (offset + rng.uniform(-spacing * 0.2, spacing * 0.2))
                t = np.arange(-reach / 2, reach / 2, 6.0)
                pts = origin + np.outer(t, direction)
                inside = (pts[:, 0] >= 0) & (pts[:, 0] < W) & (pts[:, 1] >= 0) & (pts[:, 1] < H)
                ok = np.zeros(len(pts), bool)
                ok[inside] = region[pts[inside, 1].astype(int), pts[inside, 0].astype(int)]
                # Split into runs; short hand strokes rather than ruler lines.
                run = []
                for keep, pt in zip(ok, pts):
                    if keep and len(run) < rng.integers(10, 26):
                        run.append(pt)
                        continue
                    if len(run) >= 4:
                        seg = np.array(run)
                        self.items.append(self._item([(seg, False, False)], seg[len(seg) // 2], spacing,
                                                     appear=int(seg[0][0] / W * 10), width=1.3, wobble=0.9,
                                                     depth=subject_depth - 0.03))
                    run = [pt] if keep else []

    def _place_radial(self, frame, matte):
        """Comic focus lines converging on the subject, plus broadcast arcs around the head."""
        self.items = []
        back, subject_depth = self._backdrop(matte)
        ys, xs = np.where(matte > 128)
        cx, cy = (xs.mean(), ys.min() + (ys.max() - ys.min()) * 0.25) if len(xs) else (W / 2, H / 2)
        head = (ys.max() - ys.min()) * 0.28 if len(xs) else 120
        rng = np.random.default_rng(self.seed)
        for k, a in enumerate(np.linspace(0, 2 * math.pi, 34, endpoint=False)):
            a += rng.uniform(-0.05, 0.05)
            r0, r1 = head * rng.uniform(1.9, 2.6), head * rng.uniform(4.2, 6.5)
            seg = np.array([[cx + math.cos(a) * r, cy + math.sin(a) * r] for r in np.linspace(r0, r1, 10)])
            self.items.append(self._item([(seg, False, False)], seg[0], head * 0.3, appear=k % 6, width=2.8, wobble=1.2, depth=1.0))
        for j, radius in enumerate((1.25, 1.5, 1.75)):
            for side in (-1, 1):
                arc = circle_pts(14, head * radius, head * radius, cx, cy, math.pi / 2 - side * 0.75 * math.pi / 2 - 0.45 + (math.pi if side < 0 else 0), 0.9)
                self.items.append(self._item([(arc, False, False)], arc[7], head * 0.3, appear=6 + j * 3, width=2.6, wobble=1.0,
                                             depth=1.0, colour=self.colours[-1]))

    def _place_staff(self, frame, matte):
        """Two hand-drawn music staves flowing across the table, with notes riding them."""
        self.items = []
        back, subject_depth = self._backdrop(matte)
        rng = np.random.default_rng(self.seed)
        for k, (y0, amp, phase) in enumerate(((0.3, 0.07, 0.4), (0.74, 0.06, 2.1))):
            xs = np.linspace(-0.05, 1.05, 60) * W
            gap = self.size * 0.22
            base_y = H * y0 + H * amp * np.sin(xs / W * 2 * math.pi * 1.2 + phase)
            for line in range(5):
                seg = np.stack([xs, base_y + (line - 2) * gap], 1)
                self.items.append(self._item([(seg, False, False)], seg[30], self.size, appear=k * 6 + line, width=2.4, wobble=1.0,
                                             depth=None))
            for x in np.linspace(0.12, 0.88, 6) * W + rng.uniform(-30, 30, 6):
                y = H * y0 + H * amp * math.sin(x / W * 2 * math.pi * 1.2 + phase) + rng.integers(-2, 3) * gap
                parts = [((p * self.size * 0.45) + [x, y], c, f) for p, c, f in shape('note' if rng.random() < 0.6 else 'notes')]
                self.items.append(self._item([(resample(np.asarray(q, float), c), c, f) for q, c, f in parts], (x, y), self.size * 0.45,
                                             appear=k * 6 + 8 + int(rng.integers(0, 8)), width=3.0, colour=self.colours[-1]))

    def _place_motifs(self, frame, matte):
        rng = np.random.default_rng(self.seed)
        depth = self.depths[0]
        near_subject = np.asarray(Image.fromarray(matte).filter(ImageFilter.MaxFilter(31)), np.float32) / 255
        subject_depth = float(np.median(depth[matte > 128])) if (matte > 128).any() else 1.0
        smooth = _blur_up((depth * 255).astype(np.uint8), 4, 3) / 255
        gy, gx = np.gradient(smooth)
        self.items, taken, tries = [], [], 0
        subject_depth = min(subject_depth, 1.0)
        while len(self.items) < self.count and tries < 4000:
            tries += 1
            x, y = rng.uniform(0.06, 0.94) * W, rng.uniform(0.08, 0.92) * H
            xi, yi = int(x), int(y)
            d = float(depth[yi, xi])
            if near_subject[yi, xi] > 0.05 or d > subject_depth + 0.04:
                continue  # background or the subject's own surface (a tabletop), never on or next to the subject
            size = self.size * (0.7 + 0.6 * d)
            if any((x - tx) ** 2 + (y - ty) ** 2 < (0.9 * (size + ts)) ** 2 for tx, ty, ts in taken):
                continue
            taken.append((x, y, size))
            kind = self.kinds[len(self.items) % len(self.kinds)]
            angle = math.radians(float(rng.uniform(-35, 35)))
            rot = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
            # Foreshorten along the depth gradient: strokes lie on the surface, not face the camera.
            g = np.array([gx[yi, xi], gy[yi, xi]])
            mag = float(np.linalg.norm(g))
            normal = g / mag if mag > 1e-6 else np.array([0.0, 1.0])
            squash = max(0.35, 1 / (1 + mag * 250))
            parts = []
            for pts, closed, filled in shape(kind):
                q = resample(np.asarray(pts, float), closed) @ rot.T
                q = q - np.outer(q @ normal, normal) * (1 - squash)
                parts.append((q * size + [x, y], closed, filled))
            self.items.append(self._item(parts, (x, y), size, int(rng.integers(0, 10)), colour=self.colours[len(self.items) % len(self.colours)]))

    def report(self, name):
        print(f'  scene paint {name}: {len(self.items)} doodles placed', flush=True)

    def _motion(self, i, matte):
        """The frame's motion, computed once per frame (not once per stroke): a callable pts -> pts."""
        if self.flow is None:  # still: known push about the centre
            z0 = 1 + self.push * i / max(1, self.n - 1)
            z1 = 1 + self.push * (i + 1) / max(1, self.n - 1)
            c = np.array([W / 2, H / 2])
            return lambda pts: c + (pts - c) * (z1 / z0)
        field = self.flow[min(i, len(self.flow) - 1)]
        if self.track == 'global':
            # Robust camera motion: median flow over the background only.
            bg = np.asarray(Image.fromarray(matte).resize((W // 2, H // 2)), np.float32) < 40
            motion = np.median(field[bg], axis=0) if bg.any() else np.zeros(2)
            return lambda pts: pts + motion
        return lambda pts: pts + _bilinear(field, pts[:, 0], pts[:, 1])

    def advance(self, i, matte):
        move = self._motion(i, matte)
        for item in self.items:
            item['anchor'] = move(item['anchor'][None])[0]
            item['parts'] = [(move(p), c, f) for p, c, f in item['parts']]

    def composite(self, base, i, frame, matte):
        """Paint the doodles into frame i (a uint8 RGB array) and return the result."""
        paint = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
        ref = Image.new('L', (W * SS, H * SS), 0)
        dp, dr = ImageDraw.Draw(paint), ImageDraw.Draw(ref)
        depth = self.depths[min(i, len(self.depths) - 1)]
        for item in self.items:
            age = i - item['appear']
            if age < 0:
                continue
            ax, ay = np.clip(item['anchor'], [0, 0], [W - 1, H - 1])
            surface = item['depth'] if item['depth'] is not None else float(depth[int(ay), int(ax)])
            reveal = min(1.0, (age + 1) / 5)  # draw-on: the stroke is laid down over 5 frames
            boil = age // 2
            width = item['width'] * SS
            for k, (pts, closed, filled) in enumerate(item['parts']):
                wob = pts + (np.random.default_rng(item['seed'] + boil * 97 + k).normal(0, item['wobble'], pts.shape))
                cut = max(2, int(len(wob) * reveal))
                line = [(float(x * SS), float(y * SS)) for x, y in wob[:cut]]
                if filled and reveal >= 1 and len(line) > 2:
                    dp.polygon(line, fill=item['colour'] + (255,))
                    dr.polygon(line, fill=int(surface * 255))
                dp.line(line, fill=item['colour'] + (255,), width=int(width), joint='curve')
                dr.line(line, fill=int(surface * 255), width=int(width), joint='curve')
        paint = np.asarray(paint.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.5)), np.float32)
        ref = np.asarray(ref.resize((W, H), Image.BILINEAR), np.float32) / 255
        alpha = paint[..., 3] / 255
        # Occlusion: anything nearer than the painted surface (subject, furniture, foliage) covers the paint.
        visible = np.clip(1 - (depth - ref - 0.04) / 0.05, 0, 1)
        visible *= 1 - np.asarray(Image.fromarray(matte).filter(ImageFilter.MaxFilter(5)), np.float32) / 255
        # Lighting: the paint takes the local light and a little of the local colour.
        scene = frame.astype(np.float32)
        light = _blur_up(np.clip(scene.mean(-1), 0, 255).astype(np.uint8)) / 255
        # Marker paint reads even in shadow, but still falls off with the local light.
        shade = np.clip(0.62 + 0.75 * light ** 0.6, 0.6, 1.2)[..., None]
        tint = np.stack([_blur_up(frame[..., c].copy()) for c in range(3)], -1) / 255
        rgb = paint[..., :3] * shade * (0.88 + 0.22 * tint)
        a = (alpha * visible * self.opacity)[..., None]
        out = base.astype(np.float32)
        if self.dim:
            # Knock the background back (not the subject) so it reads as a drawn backdrop behind them.
            keep = np.asarray(Image.fromarray(matte).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3)), np.float32)[..., None] / 255
            ramp = min(1.0, (i + 1) / 8)
            out = out * (keep + (1 - keep) * (1 - self.dim * ramp))
        return (out * (1 - a) + np.clip(rgb, 0, 255) * a).astype(np.uint8)


# ---------------------------------------------------------------- psychedelic burst

GY, GX = np.mgrid[0:H, 0:W].astype(np.float32)


def sample(img, x, y):
    x = np.clip(x, 0, W - 1.001)
    y = np.clip(y, 0, H - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    top = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    bottom = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bottom * fy


def hue_rotate(img, degrees, saturation=1.0):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    i = 0.596 * r - 0.274 * g - 0.322 * b
    q = 0.211 * r - 0.523 * g + 0.312 * b
    a = math.radians(degrees)
    i, q = (i * math.cos(a) - q * math.sin(a)) * saturation, (i * math.sin(a) + q * math.cos(a)) * saturation
    return np.stack([y + 0.956 * i + 0.621 * q, y - 0.272 * i - 0.647 * q, y - 1.106 * i + 1.703 * q], -1)


def kaleidoscope(frame, strength, phase):
    """Mirror the frame into a rotating 6-fold kaleidoscope, pushed toward hot pink/violet."""
    if strength <= 0:
        return frame
    img = frame.astype(np.float32)
    cx, cy = W / 2, H / 2
    dx, dy = GX - cx, GY - cy
    r = np.hypot(dx, dy) * (0.8 - 0.15 * strength)
    seg = 2 * math.pi / 6
    theta = np.mod(np.arctan2(dy, dx) + phase, seg)
    theta = np.where(theta > seg / 2, seg - theta, theta) - phase * 0.5
    k = sample(img, cx + r * np.cos(theta), cy + r * np.sin(theta))
    k = hue_rotate(k, 70 + phase * 60, 1.8)
    k = np.clip(k * 1.15 + np.array([40, 0, 35]) * strength, 0, 255)
    return (img * (1 - strength) + k * strength).astype(np.uint8)


BURST_OUT = [0.35, 0.7, 1.0]
BURST_IN = [1.0, 0.8, 0.45, 0.15]


# ---------------------------------------------------------------- the edit

def still(path, name):
    return ('still', path, name)


def clip(name, start=0.0, zoom=1.0):
    return ('clip', name, start, zoom)


def shot(slug, source, seconds, enter, outline_colour, doodles, grade=(), split=None, background=None):
    """enter: 'burst' (kaleidoscope) or a collage transition ('cut', 'whip', 'zoom', 'spin', 'slam', 'drop').
    grade: [(from_s, to_s, 'bw'|'duotone')] quick treatment flips; the doodles stay in colour on top.
    split: optional (layout, [cached clip names of the same project], arrivals) for a split screen.
    background: optional ScenePaint, doodles painted into the scene behind the subject (alternates with foreground doodles)."""
    return dict(slug=slug, source=source, seconds=seconds, enter=enter, outline=outline_colour, doodles=doodles,
                grade=list(grade), split=split, background=background)


NOTLD = 'night-of-the-living-dead-ltx-contest'
EDIT = [
    # Newest project opens the reel.
    shot('polar-bear-walk', clip('bear_walk', 0.2), 3.0, 'cut', None, [
        Doodle('crown', 0.1, -0.1, 0.1, ACID, 4, rot=-8, anchor='follow'), Doodle('motion', 1.08, 0.45, 0.12, WHITE, 8, anchor='follow'),
        Doodle('sparkle', 0.55, -0.14, 0.07, WHITE, 14, anchor='follow'), Doodle('heart', -0.1, 0.32, 0.07, PINK, 20, rot=-12, anchor='follow'),
        Doodle('star', 0.9, -0.08, 0.06, ACID, 28, anchor='follow', spin=4)]),
    shot('f1r-live-video', clip('f1r_singer', 0.2), 2.25, 'burst', PINK, [
        Doodle('notes', 0.95, 0.12, 0.2, WHITE, 3, rot=12), Doodle('heart', 0.08, 0.2, 0.13, PINK, 8, rot=-15),
        Doodle('sparkle', 0.85, 0.55, 0.1, ACID, 13), Doodle('heart', 1.05, 0.45, 0.09, PINK, 18, rot=20),
        Doodle('note', 0.05, 0.62, 0.14, WHITE, 24, rot=-10)], grade=[(1.25, 1.75, 'bw')]),
    # Hard-cut flurry: quick flips before the forest holds.
    shot('dark-forest', clip('forest_anime', 3.0), 0.5, 'cut', None, []),
    shot(NOTLD, clip('notld_carry', 2.6), 0.5, 'cut', None, [], grade=[(0, 1, 'duotone')]),
    shot('daft-punk-cover-art', still(f'{ART}/daft-punk-cover-art/01-vlx-maftei-finalupscaled.jpg', 'daft'), 0.625, 'cut', None, []),
    shot('dark-forest', clip('forest_boy_a', 0.5), 3.25, 'burst', None, [Doodle('rays', -0.05, 0.42, 0.13, ACID, 2, anchor='follow', spin=1.5)], background=ScenePaint([(214, 226, 214)], ['ghost', 'peeker', 'eyeblob', 'ghost', 'peeker'], 21, count=9, size=92, track='dense', opacity=0.95)),
    shot(NOTLD, clip('notld_carry', 0.3), 1.0, 'cut', ACID, [
        Doodle('drops', 0.25, 0.08, 0.12, WHITE, 2), Doodle('motion', -0.08, 0.45, 0.14, WHITE, 5),
        Doodle('bang', 0.62, 0.1, 0.12, ACID, 9)]),
    shot(NOTLD, clip('notld_armchair', 0.5), 2.75, 'spin', None, [Doodle('skull', 0.2, -0.12, 0.2, WHITE, 3, rot=-10)], background=ScenePaint([(222, 230, 220)], seed=22, size=13, track='global', mode='hatch', opacity=0.55, dim=0.35), grade=[(1.0, 1.5, 'duotone')]),
    # Split: four NOTLD shots not used elsewhere in the reel slam in one by one, doodles on top.
    shot(NOTLD, clip('notld_tv', 0.2), 1.75, 'slam', None, [
        Doodle('bolt', 0.47, 0.42, 0.12, ACID, 6, anchor='frame', rot=-12), Doodle('skull', 0.92, 0.12, 0.1, WHITE, 12, anchor='frame', rot=10),
        Doodle('sparkle', 0.08, 0.9, 0.09, PINK, 16, anchor='frame')],
         split=('grid', ['notld_watch', 'notld_sofa', 'notld_horde', 'notld_anchor'], (0, 4, 9, 13))),
    # Second flurry before the presenter.
    shot('trips', still(f'{ART}/trips/07-vlx-maftei-landscapes-07.jpg', 'trips_rock'), 0.5, 'cut', None, [], grade=[(0, 1, 'bw')]),
    shot('cat-walkman', still(f'{ART}/cat-walkman/01-vlx-maftei-catwalkmanhighrezblurred2.jpg', 'cat'), 0.5, 'cut', None, [], grade=[(0, 1, 'duotone')]),
    shot(NOTLD, clip('notld_presenter', 0.4), 3.0, 'burst', PINK, [Doodle('halo', 0.5, -0.06, 0.12, ACID, 3)], background=ScenePaint([WHITE, PINK], seed=23, track='global', mode='radial', opacity=0.9), grade=[(0.75, 1.25, 'bw')]),
    shot('daft-punk-cover-art', still(f'{ART}/daft-punk-cover-art/01-vlx-maftei-finalupscaled.jpg', 'daft'), 1.25, 'cut', None, [
        Doodle('halo', 0.24, 0.12, 0.09, ACID, 2, anchor='frame'), Doodle('halo', 0.74, 0.1, 0.09, ACID, 6, anchor='frame'),
        Doodle('star', 0.12, 0.3, 0.06, WHITE, 10, anchor='frame', spin=4), Doodle('motion', 0.9, 0.62, 0.08, WHITE, 14, anchor='frame'),
        Doodle('star', 0.52, 0.26, 0.05, PINK, 20, anchor='frame', spin=-5), Doodle('sparkle', 0.86, 0.3, 0.06, ACID, 26, anchor='frame')],
         grade=[]),
    shot('cat-walkman', still(f'{ART}/cat-walkman/01-vlx-maftei-catwalkmanhighrezblurred2.jpg', 'cat'), 2.5, 'zoom', WHITE, [Doodle('heart_eyes', 1.25, 0.15, 0.26, PINK, 3, rot=8)], background=ScenePaint([(246, 236, 214), PINK], seed=24, size=78, mode='staff', opacity=0.9)),
    shot('trips', still(f'{ART}/trips/07-vlx-maftei-landscapes-07.jpg', 'trips_rock'), 0.75, 'drop', ACID, [
        Doodle('arrow', 0.5, 1.25, 0.25, WHITE, 3), Doodle('sparkle', 0.15, 0.9, 0.2, ACID, 7), Doodle('spiral', 0.85, 0.35, 0.18, WHITE, 12, spin=5)],
         grade=[(0, 1, 'duotone')]),
    shot('fugi-visualizer', still(f'{FUGI}/reference-tongue-in.png', 'fugi'), 3.0, 'burst', None, [Doodle('crown', 0.5, -0.02, 0.14, ACID, 2)], background=ScenePaint([(255, 150, 210)], ['rabbit'], 25, count=16, size=66, opacity=0.8), grade=[(1.25, 1.75, 'bw')]),
    shot('dark-forest', clip('forest_anime', 0.3), 1.75, 'cut', ACID, [
        Doodle('rays', 1.0, 0.42, 0.13, ACID, 2, anchor='follow', spin=-1.5), Doodle('eyes', 0.34, 0.12, 0.05, WHITE, 8, anchor='frame'),
        Doodle('eyes', 0.73, 0.18, 0.045, WHITE, 14, anchor='frame'), Doodle('heart', -1.2, -0.1, 0.09, PINK, 20, anchor='follow'),
        Doodle('star', 2.2, -0.2, 0.09, ACID, 28, anchor='follow', spin=6)]),
]


def render_shot(s, frames_n):
    spec = s['source']
    frames, mattes = load_clip(spec[1], spec[2], frames_n, spec[3]) if spec[0] == 'clip' else load_still(spec[1], spec[2], frames_n)
    frames_n = min(frames_n, len(frames), len(mattes))
    if s['split']:
        layout, names, arrivals = s['split']
        pieces = [load_clip(name, spec[2], frames_n)[0] for name in names]
        frames = [COLLAGE.split(pieces, i, layout, i, list(arrivals)) for i in range(frames_n)]
    boxes = smooth_boxes(mattes[:frames_n])
    scene_paint = s['background']
    if scene_paint:
        scene_paint.prepare(spec, frames, mattes, frames_n)
        scene_paint.report(spec[1] if spec[0] == 'clip' else spec[2])
    out = []
    for i in range(frames_n):
        f = frames[i]
        for start, end, kind in s['grade']:
            if start * FPS <= i < end * FPS:
                f = COLLAGE.bw(f) if kind == 'bw' else COLLAGE.duotone(f)
        base = Image.fromarray(np.ascontiguousarray(f)).convert('RGBA')
        if scene_paint:
            base = Image.fromarray(scene_paint.composite(np.asarray(base.convert('RGB')), i, frames[i], mattes[i])).convert('RGBA')
            scene_paint.advance(i, mattes[i])
        if s['outline'] is not None and i >= 1:
            base.alpha_composite(outline(mattes[i], i, s['outline']))
        layer = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for d in s['doodles']:
            d.draw(draw, i, boxes[i])
        base.alpha_composite(layer.resize((W, H), Image.LANCZOS))
        out.append(np.asarray(base.convert('RGB')))
    return out


def _render_to_disk(args):
    index, folder = args
    s = EDIT[index]
    started = time.time()
    frames = render_shot(s, round(s['seconds'] * FPS))
    path = Path(folder) / f'{index:02d}.npy'
    np.save(path, np.stack(frames))
    return index, str(path), time.time() - started


def render_all():
    """Render every shot in its own process (shots are independent), reporting each as it lands."""
    started = time.time()
    with tempfile.TemporaryDirectory(prefix='doodle-') as folder:
        ctx = multiprocessing.get_context('fork')
        results = {}
        with ctx.Pool(min(len(EDIT), os.cpu_count() or 4)) as pool:
            for index, path, seconds in pool.imap_unordered(_render_to_disk, [(k, folder) for k in range(len(EDIT))]):
                results[index] = list(np.load(path))
                print(f'  shot {index + 1:2d}/{len(EDIT)} {EDIT[index]["slug"]:<38} {seconds:5.1f}s', flush=True)
    print(f'  all shots rendered in {time.time() - started:.1f}s', flush=True)
    return [results[k] for k in range(len(EDIT))]


def main():
    projects = json.loads((ROOT / 'content/manual-projects.json').read_text())
    overrides = json.loads((ROOT / 'content/project-overrides.json').read_text())
    titles = {p['slug']: {**p, **overrides.get(p['slug'], {})}['title'] for p in projects}
    tools = {'polar-bear-walk': ['MiniMax H3', 'Blender', 'LTX-2.5'], 'dark-forest': ['Hunyuan3D', 'Kimodo', 'Blender'], 'f1r-live-video': ['LTX-2.3', 'Pi3X point cloud'],
             NOTLD: ['ComfyUI', 'LTX-2'], 'fugi-visualizer': ['Codex', 'WebGL'],
             'trips': ['Flux', 'Runway'], 'daft-punk-cover-art': ['ComfyUI', 'SDXL'], 'cat-walkman': ['SDXL', 'Suno']}
    shots = render_all()
    # Cuts: kaleidoscope bursts or the collage's motion-blurred transitions.
    phase = 0.0
    for index, s in enumerate(EDIT):
        if index == 0 or s['enter'] == 'cut':
            continue
        prev, cur = shots[index - 1], shots[index]
        if s['enter'] == 'burst':
            for k, strength in enumerate(BURST_OUT):
                j = len(prev) - len(BURST_OUT) + k
                prev[j] = kaleidoscope(prev[j], strength, phase + k * 0.25)
            for k, strength in enumerate(BURST_IN):
                cur[k] = kaleidoscope(cur[k], strength, phase + (len(BURST_OUT) + k) * 0.25)
            phase += 1.3
            continue
        out_n, in_n = COLLAGE.TRANSITION_FRAMES[s['enter']]
        for j in range(in_n):
            cur[j] = COLLAGE.transition_in(cur[j], s['enter'], j / in_n, (j + 1) / in_n)
        for j in range(out_n):
            k = len(prev) - out_n + j
            prev[k] = COLLAGE.transition_out(prev[k], s['enter'], j / out_n, (j + 1) / out_n)

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'reel-doodle-720.mp4'
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                            *ENCODER, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)],
                           stdin=subprocess.PIPE)
    manifest, t = [], 0.0
    for s, frames in zip(EDIT, shots):
        for f in frames:
            enc.stdin.write(np.ascontiguousarray(f).tobytes())
        dur = len(frames) / FPS
        if manifest and manifest[-1]['slug'] == s['slug']:
            manifest[-1]['end'] = round(t + dur, 3)
        else:
            manifest.append({'start': round(t, 3), 'end': round(t + dur, 3), 'slug': s['slug'], 'title': titles[s['slug']],
                             'tools': tools.get(s['slug'], [])})
        t += dur
        print(f"{s['slug']:<40} {dur:4.2f}s {s['enter']}", flush=True)
    enc.stdin.close()
    enc.wait()
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(target), '-vf', 'scale=854:480', *ENCODER_SMALL,
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT / 'reel-doodle-480.mp4')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '1.5', '-i', str(target), '-frames:v', '1', '-q:v', '4', str(OUT / 'reel-doodle-poster.jpg')], check=True)
    (OUT / 'reel-doodle.json').write_text(json.dumps({'duration': round(t, 3), 'shots': manifest}, indent=2) + '\n')
    print(f'reel-doodle: {t:.2f}s, {target.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
