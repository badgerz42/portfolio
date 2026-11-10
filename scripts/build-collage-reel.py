#!/usr/bin/env python3
"""Collage version of the hero reel.

Beat-cut edit (120 BPM, 12 frames per beat at 24 fps) of the recent work: per-cut treatments
(high-contrast black and white, acid-green duotone, circle crop), split layouts whose pieces are
different shots or regions of the same project and slam in one by one, and motion-graphics
transitions only on the cuts (whip, zoom, 3D spin, slam, drop) with motion blur. No text.

Outputs (public/assets/generated/reel/):
  reel-collage-720.mp4, reel-collage-480.mp4, reel-collage-poster.jpg, reel-collage.json

Needs ffmpeg, Pillow and numpy.   python3 scripts/build-collage-reel.py
"""
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / 'public'
OUT = PUB / 'assets/generated/reel'
W, H, FPS = 1280, 720, 24
BEAT = 12  # frames per beat (120 BPM)
ACID = (166, 255, 0)
RNG = np.random.default_rng(7)


NOTLD = 'assets/projects/night-of-the-living-dead-ltx-contest/night-of-the-living-dead-final.mp4'
F1R = 'assets/projects/f1r-live-video/f1r-live-final.mp4'
FOREST = 'assets/projects/dark-forest/dark-forest-final.mp4'
INK = 'assets/projects/dark-forest/look-dev-ink-edit.mp4'
FUGI = 'assets/projects/fugi-visualizer'
BEAR = 'assets/projects/polar-bear-walk/polar-bear-final.mp4'


# ---------------------------------------------------------------- sources

def decode(path, start, frames, focus=None):
    """Decode `frames` frames of a clip, cover-cropped to W x H (optionally reframed)."""
    zoom = (focus or {}).get('zoom', 1.0)
    sw, sh = round(W * zoom), round(H * zoom)
    if focus:
        x = f"min(max(iw*{focus['x']}-ow/2\\,0)\\,iw-ow)"
        y = f"min(max(ih*{focus['y']}-oh/2\\,0)\\,ih-oh)"
    else:
        x, y = '(iw-ow)/2', '(ih-oh)/2'
    vf = f'scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}:{x}:{y},fps={FPS},format=rgb24'
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(PUB / path), '-frames:v', str(frames), '-vf', vf, '-f', 'rawvideo', '-'],
        check=True, capture_output=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
    if len(arr) < frames:  # pad by holding the last frame
        arr = np.concatenate([arr, np.repeat(arr[-1:], frames - len(arr), 0)])
    return arr


def still(path, frames, drift=0.03, region=None):
    """A still with a slow push-in; `region` = (x, y, zoom) in source pixels frames one area of it."""
    src = Image.open(PUB / path).convert('RGB')
    zoom = region[2] if region else 1.0
    scale = max(W / src.width, H / src.height) * (1 + drift) * zoom
    base = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
    fx = region[0] * scale if region else base.width / 2
    fy = region[1] * scale if region else base.height / 2
    out = []
    for i in range(frames):
        z = 1 + drift * (1 - i / max(1, frames - 1))
        cw, ch = min(round(W * z), base.width), min(round(H * z), base.height)
        l = int(min(max(fx - cw / 2, 0), base.width - cw))
        t = int(min(max(fy - ch / 2, 0), base.height - ch))
        out.append(np.asarray(base.crop((l, t, l + cw, t + ch)).resize((W, H), Image.BILINEAR)))
    return np.stack(out)


_CUTS = {}


def cuts_in(path):
    """Edit-cut times (seconds) in a source video, from frame differencing (cached)."""
    if path not in _CUTS:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(PUB / path), '-vf', f'fps={FPS},scale=160:90,format=gray', '-f', 'rawvideo', '-'],
                             check=True, capture_output=True).stdout
        f = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
        diff = np.abs(np.diff(f, axis=0)).mean((1, 2))
        _CUTS[path] = [(i + 1) / FPS for i in np.where(diff > max(15, float(np.median(diff)) * 6))[0]]
    return _CUTS[path]


def load(spec, frames):
    """('clip', path, start[, focus]) | ('still', path) | ('crop', path, (x, y, zoom))."""
    if spec[0] == 'clip':
        start, end = spec[2], spec[2] + frames / FPS
        crossing = [t for t in cuts_in(spec[1]) if start < t < end]
        if crossing:
            # A cut inside a card flashes a second shot for a few frames: pick a clean start instead.
            raise SystemExit(f'{spec[1]} {start:.2f}-{end:.2f}s crosses an edit cut at {crossing[0]:.2f}s')
        return decode(spec[1], spec[2], frames, spec[3] if len(spec) > 3 else None)
    return still(spec[1], frames, region=spec[2] if spec[0] == 'crop' else None)


# ---------------------------------------------------------------- treatments

def bw(f):
    # Auto-levels per frame, then a hard S-curve, so dark footage still reads as punchy black and white.
    g = f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114
    lo, hi = np.percentile(g[::4, ::4], (2, 99.5))
    g = np.clip((g - lo) / max(hi - lo, 24), 0, 1)
    g = np.clip((g - 0.5) * 1.5 + 0.5, 0, 1) * 255
    return np.repeat(g[..., None], 3, 2).astype(np.uint8)


def duotone(f):
    g = (f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114) / 255
    g = np.clip((g - 0.15) * 1.6, 0, 1)[..., None]
    return (g * np.array(ACID) + (1 - g) * np.array([2, 6, 2])).astype(np.uint8)


# ---------------------------------------------------------------- motion

def back_out(t, overshoot=1.9):
    """Ease-out with overshoot: lands past the target and settles (the motion-graphics 'slam')."""
    t = min(max(t, 0.0), 1.0) - 1
    return 1 + t * t * ((overshoot + 1) * t + overshoot)


def expo_in(t):
    t = min(max(t, 0.0), 1.0)
    return 0.0 if t == 0 else 2 ** (10 * t - 10)


def transform(img, dx=0.0, dy=0.0, scale=1.0, rot=0.0, yaw=0.0):
    """Move/scale/rotate a frame (and optionally swing it in 3D around its vertical axis) over black."""
    im = Image.fromarray(img)
    if yaw:
        # Perspective 'card flip': the far edge shrinks as the frame turns.
        a = math.radians(yaw)
        half = W / 2 * math.cos(a)
        depth = 1 + 0.55 * math.sin(abs(a))
        near_h, far_h = H / 2, H / 2 / depth
        left_h, right_h = (far_h, near_h) if yaw > 0 else (near_h, far_h)
        quad = [(W / 2 - half, H / 2 - left_h), (W / 2 + half, H / 2 - right_h), (W / 2 + half, H / 2 + right_h), (W / 2 - half, H / 2 + left_h)]
        rows, rhs = [], []
        for (u, v), (x, y) in zip(quad, [(0, 0), (W, 0), (W, H), (0, H)]):
            rows.append([u, v, 1, 0, 0, 0, -x * u, -x * v]); rhs.append(x)
            rows.append([0, 0, 0, u, v, 1, -y * u, -y * v]); rhs.append(y)
        coeffs = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
        im = im.transform((W, H), Image.PERSPECTIVE, tuple(coeffs), Image.BILINEAR)
    if scale != 1.0 or rot or dx or dy:
        c, s_ = math.cos(math.radians(rot)) / scale, math.sin(math.radians(rot)) / scale
        cx, cy = W / 2 + dx, H / 2 + dy
        # Inverse affine: output pixel -> source pixel.
        im = im.transform((W, H), Image.AFFINE, (c, s_, W / 2 - c * cx - s_ * cy, -s_, c, H / 2 + s_ * cx - c * cy), Image.BILINEAR)
    return np.asarray(im)


def blurred(img, params_at, samples=6):
    """Motion blur: average the frame across its shutter (params_at(0..1) -> transform kwargs)."""
    acc = np.zeros((H, W, 3), np.float32)
    for k in range(samples):
        acc += transform(img, **params_at(k / max(1, samples - 1)))
    return (acc / samples).astype(np.uint8)


# Transitions: (frames at the end of the outgoing card, frames at the start of the incoming card).
TRANSITION_FRAMES = {'cut': (0, 0), 'whip': (3, 4), 'zoom': (2, 5), 'spin': (3, 4), 'slam': (0, 5), 'drop': (0, 5)}


def transition_out(img, kind, u0, u1):
    """Outgoing card during frames u0..u1 (0..1 across its exit)."""
    if kind == 'whip':
        return blurred(img, lambda k: {'dx': -W * 1.1 * expo_in(u0 + (u1 - u0) * k)})
    if kind == 'zoom':
        return blurred(img, lambda k: {'scale': 1 + 0.9 * expo_in(u0 + (u1 - u0) * k)})
    if kind == 'spin':
        return blurred(img, lambda k: {'yaw': 85 * expo_in(u0 + (u1 - u0) * k)}, samples=4)
    return img


def transition_in(img, kind, u0, u1):
    """Incoming card during frames u0..u1 (0..1 across its entrance)."""
    if kind == 'whip':
        return blurred(img, lambda k: {'dx': W * 1.1 * (1 - back_out(u0 + (u1 - u0) * k, 1.2))})
    if kind == 'zoom':
        return blurred(img, lambda k: {'scale': 1 + 0.6 * (1 - back_out(u0 + (u1 - u0) * k, 1.6))})
    if kind == 'spin':
        return blurred(img, lambda k: {'yaw': -85 * (1 - back_out(u0 + (u1 - u0) * k, 1.1))}, samples=4)
    if kind == 'slam':
        return blurred(img, lambda k: {'scale': 1 + 0.25 * (1 - back_out(u0 + (u1 - u0) * k)), 'rot': 7 * (1 - back_out(u0 + (u1 - u0) * k))})
    if kind == 'drop':
        return blurred(img, lambda k: {'dy': -H * (1 - back_out(u0 + (u1 - u0) * k, 1.4))})
    return img


# ---------------------------------------------------------------- split layouts

# Slots as (x, y, w, h) fractions plus the direction each piece slams in from.
LAYOUTS = {
    'stack2': ([(0, 0, 1, 0.5), (0, 0.5, 1, 0.5)], ['-', 'right']),
    'stack3': ([(0, 0, 1, 1 / 3), (0, 1 / 3, 1, 1 / 3), (0, 2 / 3, 1, 1 / 3)], ['-', 'right', 'left']),
    'cols2': ([(0, 0, 0.5, 1), (0.5, 0, 0.5, 1)], ['-', 'down']),
    'cols3': ([(0, 0, 1 / 3, 1), (1 / 3, 0, 1 / 3, 1), (2 / 3, 0, 1 / 3, 1)], ['-', 'up', 'down']),
    'grid': ([(0, 0, 0.5, 0.5), (0.5, 0, 0.5, 0.5), (0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)], ['-', 'right', 'down', 'pop']),
    'mosaic3': ([(0, 0, 0.6, 1), (0.6, 0, 0.4, 0.5), (0.6, 0.5, 0.4, 0.5)], ['-', 'up', 'pop']),
}
ARRIVE = 5  # frames for a piece to slam into its slot


def fit(frame, w, h):
    """Cover-crop a frame to a w x h slot (centre)."""
    src = Image.fromarray(frame)
    s_ = max(w / W, h / H)
    rw, rh = max(w, round(W * s_)), max(h, round(H * s_))
    src = src.resize((rw, rh), Image.BILINEAR)
    l, t = (rw - w) // 2, (rh - h) // 2
    return np.asarray(src.crop((l, t, l + w, t + h)))


def split(pieces, i, layout, local, arrivals, gap=4):
    """Pieces slam into their slots one by one (uneven `arrivals` in frames), with overshoot and blur."""
    slots, directions = LAYOUTS[layout]
    out = np.zeros((H, W, 3), np.uint8)
    for k, ((fx, fy, fw, fh), direction) in enumerate(zip(slots, directions)):
        x0, y0 = round(fx * W) + (gap if fx > 0 else 0), round(fy * H) + (gap if fy > 0 else 0)
        x1, y1 = round((fx + fw) * W), round((fy + fh) * H)
        w, h = x1 - x0, y1 - y0
        tile = fit(pieces[k][i], w, h)
        start = arrivals[k] if k < len(arrivals) else 0
        u = (local - start) / ARRIVE
        if k == 0 or u >= 1:
            out[y0:y1, x0:x1] = tile
            continue
        if u <= 0:
            # Waiting slot: a dark, soft ghost of what's about to land, not a black hole.
            ghost = Image.fromarray(tile).resize((max(1, w // 12), max(1, h // 12)), Image.BILINEAR).resize((w, h), Image.BILINEAR)
            out[y0:y1, x0:x1] = (np.asarray(ghost, np.float32) * 0.22).astype(np.uint8)
            continue
        acc = np.zeros((h, w, 3), np.float32)
        for sample in range(4):  # motion blur across the frame
            p = back_out(min(u + sample * 0.05, 1.0), 1.7)
            slot = np.zeros((h, w, 3), np.uint8)
            if direction == 'pop':
                sc = max(0.05, p)
                small = np.asarray(Image.fromarray(tile).resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.BILINEAR))
                sh, sw = small.shape[:2]
                oy, ox = (h - sh) // 2, (w - sw) // 2
                if oy >= 0 and ox >= 0:
                    slot[oy:oy + sh, ox:ox + sw] = small
                else:
                    slot = small[-oy:-oy + h, -ox:-ox + w] if oy < 0 else slot
            else:
                off = (1 - p)
                dx = {'right': off * w, 'left': -off * w}.get(direction, 0)
                dy = {'down': -off * h, 'up': off * h}.get(direction, 0)
                sx, sy = int(round(dx)), int(round(dy))
                xs0, xs1 = max(0, sx), min(w, w + sx)
                ys0, ys1 = max(0, sy), min(h, h + sy)
                if xs1 > xs0 and ys1 > ys0:
                    slot[ys0:ys1, xs0:xs1] = tile[ys0 - sy:ys1 - sy, xs0 - sx:xs1 - sx]
            acc += slot
        out[y0:y1, x0:x1] = (acc / 4).astype(np.uint8)
    return out


def circle(f, i, total):
    """Black frame, circular black-and-white crop, rotating ring of text (the 'clock' shot)."""
    canvas = Image.new('RGB', (W, H), (4, 5, 5))
    radius = int(H * 0.36)
    cx, cy = W // 2, H // 2
    disc = Image.fromarray(bw(f)).crop((cx - radius, cy - radius, cx + radius, cy + radius))
    mask = Image.new('L', disc.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, disc.width - 1, disc.height - 1), fill=255)
    canvas.paste(disc, (cx - radius, cy - radius), mask)
    d = ImageDraw.Draw(canvas)
    d.ellipse((cx - radius - 6, cy - radius - 6, cx + radius + 6, cy + radius + 6), outline=(240, 242, 236), width=3)
    # A second thin ring that slowly widens, instead of text.
    grow = 18 + int(22 * i / max(1, total - 1))
    d.ellipse((cx - radius - grow, cy - radius - grow, cx + radius + grow, cy + radius + grow), outline=(110, 116, 110), width=1)
    return np.asarray(canvas)


# ---------------------------------------------------------------- edit

MIN_FRAMES = 12  # 0.5 s: fast, but never a flash


def card(slug, source, beats, segments, split=(), enter='cut', arrivals=(0, 5, 11, 15)):
    """segments: [(beats, treatment)]; a treatment 'split:<layout>' uses the card's distinct `split`
    sources (same project, other shots or other regions). `enter`: transition into this card."""
    layouts = [t.split(':', 1)[1] for _, t in segments if t.startswith('split:')]
    for layout in layouts:
        need = len(LAYOUTS[layout][0])
        if len(split) < need:
            raise SystemExit(f'{slug}: {layout} needs {need} different sources, got {len(split)}')
    if len({repr(spec) for spec in split}) != len(split):
        raise SystemExit(f'{slug}: split sources must all be different')
    if round(beats * BEAT) < MIN_FRAMES:
        raise SystemExit(f'{slug}: {beats} beats is under the {MIN_FRAMES}-frame minimum')
    return dict(slug=slug, source=source, beats=beats, segments=segments, split=list(split), enter=enter, arrivals=list(arrivals))


FOREST_FOCUS = {'x': 0.35, 'y': 0.6, 'zoom': 1.5}
DAFT = 'assets/artstation/daft-punk-cover-art/01-vlx-maftei-finalupscaled.jpg'
CAT = 'assets/artstation/cat-walkman/01-vlx-maftei-catwalkmanhighrezblurred2.jpg'
EDIT = [
    # Newest project opens: the walk, then head and paws side by side.
    card('polar-bear-walk', ('clip', BEAR, 2.0), 3, [(1.5, 'color'), (1.5, 'split:cols2')], arrivals=(0, 5),
         split=[('clip', BEAR, 3.5, {'x': 0.42, 'y': 0.38, 'zoom': 2.0}), ('clip', BEAR, 3.5, {'x': 0.6, 'y': 0.72, 'zoom': 2.0})]),  # head / paws
    card('f1r-live-video', ('clip', F1R, 150.0), 2, [(2, 'circle')], enter='whip'),
    card('dark-forest', ('clip', FOREST, 10.0, FOREST_FOCUS), 2, [(1, 'bw'), (1, 'color')], enter='zoom'),
    card('dark-forest', ('clip', FOREST, 12.0, FOREST_FOCUS), 1.5, [(1.5, 'split:stack2')], arrivals=(0, 4),
         split=[('clip', FOREST, 12.0, FOREST_FOCUS), ('clip', FOREST, 4.0, {'x': 0.78, 'y': 0.2, 'zoom': 1.6})]),  # boy / eyes
    card('night-of-the-living-dead-ltx-contest', ('clip', NOTLD, 59.6), 3.5, [(1, 'color'), (1, 'bw'), (1.5, 'split:cols3')],
         enter='whip', arrivals=(0, 3, 10),
         split=[('clip', NOTLD, 60.6), ('clip', NOTLD, 45.0), ('clip', NOTLD, 91.0)]),  # couch room / TV / zombie presenter
    card('night-of-the-living-dead-ltx-contest', ('clip', NOTLD, 66.0), 2.5, [(1, 'bw'), (1.5, 'split:grid')], enter='spin',
         arrivals=(0, 4, 7, 13), split=[('clip', NOTLD, 67.0), ('clip', NOTLD, 20.5), ('clip', NOTLD, 4.5), ('clip', NOTLD, 39.5)]),
    card('f1r-live-video', ('clip', F1R, 158.0), 2, [(2, 'bw')], enter='slam'),
    card('f1r-live-video', ('clip', F1R, 166.0), 1.5, [(1.5, 'duotone')]),
    # Single-image projects split into different regions of the image.
    card('daft-punk-cover-art', ('still', DAFT), 2.5, [(1, 'color'), (1.5, 'split:mosaic3')], enter='zoom', arrivals=(0, 6, 9),
         split=[('crop', DAFT, (490, 330, 2.0)), ('crop', DAFT, (1400, 360, 2.0)), ('crop', DAFT, (1180, 650, 2.6))]),
    card('cat-walkman', ('still', CAT), 2, [(2, 'split:cols2')], enter='whip', arrivals=(0, 7),
         split=[('crop', CAT, (420, 470, 2.2)), ('crop', CAT, (1300, 560, 1.8))]),
    card('trips', ('still', 'assets/artstation/trips/07-vlx-maftei-landscapes-07.jpg'), 1, [(1, 'bw')]),
    card('trips', ('still', 'assets/artstation/trips/04-vlx-maftei-landscapes-04.jpg'), 1.5, [(1.5, 'color')], enter='drop'),
    card('dark-forest', ('clip', INK, 12.0), 2.5, [(1, 'color'), (1.5, 'split:stack3')], enter='spin', arrivals=(0, 5, 8),
         split=[('clip', INK, 4.0, {'x': 0.86, 'y': 0.2, 'zoom': 2.0}), ('clip', INK, 13.0, {'x': 0.18, 'y': 0.66, 'zoom': 2.2}),
                ('clip', INK, 18.0, {'x': 0.74, 'y': 0.72, 'zoom': 1.8})]),  # ridge / boy / hollow log
    card('fugi-visualizer', ('still', f'{FUGI}/f1r-character-glitch.png'), 1, [(1, 'color')], enter='slam'),
    card('fugi-visualizer', ('still', f'{FUGI}/reference-tongue-in.png'), 1.5, [(1.5, 'bw')], enter='zoom'),
    card('night-of-the-living-dead-ltx-contest', ('clip', NOTLD, 100.0), 3, [(1, 'color'), (0.5, 'bw'), (1.5, 'split:grid')],
         enter='whip', arrivals=(0, 6, 8, 14),
         split=[('clip', NOTLD, 102.0), ('clip', NOTLD, 52.0), ('clip', NOTLD, 72.5), ('clip', NOTLD, 60.0)]),
    card('f1r-live-video', ('clip', F1R, 184.0), 2, [(2, 'circle')], enter='zoom'),
    card('dark-forest', ('clip', FOREST, 20.0, FOREST_FOCUS), 2.5, [(1, 'color'), (1.5, 'split:stack2')], enter='drop', arrivals=(0, 6),
         split=[('clip', FOREST, 21.0, FOREST_FOCUS), ('clip', FOREST, 26.0, {'x': 0.31, 'y': 0.25, 'zoom': 1.6})]),  # boy / eyes
]

TITLES = {}
TOOLS = {'polar-bear-walk': ['MiniMax H3', 'Blender', 'LTX-2.5'], 'dark-forest': ['Hunyuan3D', 'Kimodo', 'Blender'], 'f1r-live-video': ['LTX-2.3', 'Pi3X point cloud'], 'fugi-visualizer': ['Codex', 'WebGL'], 'trips': ['Flux', 'Runway']}


def load_titles():
    projects = json.loads((ROOT / 'content/manual-projects.json').read_text())
    overrides = json.loads((ROOT / 'content/project-overrides.json').read_text())
    for p in projects:
        merged = {**p, **overrides.get(p['slug'], {})}
        TITLES[p['slug']] = (merged['title'], TOOLS.get(p['slug'], merged.get('tools', [])[:2]))


def render_card(c):
    n = round(c['beats'] * BEAT)
    frames = load(c['source'], n)
    pieces = [load(spec, n) for spec in c['split']]
    treatments, starts = [], []
    for beats, t in c['segments']:
        count = round(beats * BEAT)
        starts += [len(treatments)] * count
        treatments += [t] * count
    treatments = (treatments + [treatments[-1]] * n)[:n]
    starts = (starts + [starts[-1]] * n)[:n]
    out = []
    for i in range(n):
        f, t = frames[i], treatments[i]
        if t == 'bw':
            img = bw(f)
        elif t == 'duotone':
            img = duotone(f)
        elif t.startswith('split:'):
            img = split(pieces, i, t.split(':', 1)[1], i - starts[i], c['arrivals'])
        elif t == 'circle':
            img = circle(f, i, n)
        else:
            img = f
        out.append(np.asarray(img))
    return out


def apply_transitions(cards):
    """Kinetic moves only at cuts: the outgoing card exits and the incoming one enters (with motion blur)."""
    for index, frames in enumerate(cards):
        kind = EDIT[index]['enter']
        out_n, in_n = TRANSITION_FRAMES[kind]
        if in_n:
            for j in range(min(in_n, len(frames))):
                frames[j] = transition_in(frames[j], kind, j / in_n, (j + 1) / in_n)
        if out_n and index > 0:
            prev = cards[index - 1]
            for j in range(out_n):
                k = len(prev) - out_n + j
                prev[k] = transition_out(prev[k], kind, j / out_n, (j + 1) / out_n)
    return cards


def main():
    load_titles()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'reel-collage-720.mp4'
    enc = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
         '-c:v', 'libx264', '-preset', 'slow', '-crf', '26', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)],
        stdin=subprocess.PIPE)
    shots, t = [], 0.0
    grain = RNG.integers(-4, 5, (4, H, W, 1), dtype=np.int16)
    frame_no = 0
    rendered = apply_transitions([list(render_card(c)) for c in EDIT])
    for c, frames in zip(EDIT, rendered):
        for f in frames:
            noisy = np.clip(f.astype(np.int16) + grain[frame_no % 4], 0, 255).astype(np.uint8)
            enc.stdin.write(noisy.tobytes())
            frame_no += 1
        dur = len(frames) / FPS
        title, tools = TITLES[c['slug']]
        if shots and shots[-1]['slug'] == c['slug']:
            shots[-1]['end'] = round(t + dur, 3)
        else:
            shots.append({'start': round(t, 3), 'end': round(t + dur, 3), 'slug': c['slug'], 'title': title, 'tools': tools})
        t += dur
        print(f"{c['slug']:<40} {dur:4.2f}s")
    enc.stdin.close()
    enc.wait()
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(target), '-vf', 'scale=854:480', '-c:v', 'libx264', '-preset', 'slow', '-crf', '26',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT / 'reel-collage-480.mp4')], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '2.6', '-i', str(target), '-frames:v', '1', '-q:v', '4', str(OUT / 'reel-collage-poster.jpg')], check=True)
    (OUT / 'reel-collage.json').write_text(json.dumps({'duration': round(t, 3), 'shots': shots}, indent=2) + '\n')
    print(f'reel-collage: {t:.2f}s, {target.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
