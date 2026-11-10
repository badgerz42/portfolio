#!/usr/bin/env python3
"""Generate depth passes and subject mattes through a local ComfyUI (http://127.0.0.1:8188).

  python3 scripts/comfy-passes.py video <clip.mp4> <out_dir>               # depth, DepthCrafter
  python3 scripts/comfy-passes.py image <image> <out_dir>                  # depth, Depth Anything V2
  python3 scripts/comfy-passes.py matte-video <clip.mp4> <out_dir> "boy"   # SAM3 text-prompted video matte
  python3 scripts/comfy-passes.py matte-image <image> <out_dir> "cat" [threshold]  # SAM3 text-prompted matte
  python3 scripts/comfy-passes.py matte-points <image> <out_dir> '[{"x": 360, "y": 420}]'  # SAM3 click-prompted matte

Frames are written as PNGs into <out_dir> (depth: white = near; mattes: white = subject).
Uses only models already installed in ComfyUI; nothing is downloaded.
"""
import os
import json
import shutil
import sys
import time
import urllib.request
import uuid
from pathlib import Path

API = 'http://127.0.0.1:8188'
# Where the running ComfyUI saves images (its --output-directory); override with COMFY_OUTPUT.
COMFY_OUTPUT = Path(os.environ.get('COMFY_OUTPUT', '/mnt/Programs4/ComfyUI/output'))


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read())


def run(graph, prefix):
    prompt_id = call('/prompt', {'prompt': graph, 'client_id': str(uuid.uuid4())})['prompt_id']
    while True:
        history = call(f'/history/{prompt_id}')
        if prompt_id in history:
            status = history[prompt_id].get('status', {})
            if status.get('status_str') == 'error':
                raise RuntimeError(json.dumps(status.get('messages', []))[-1500:])
            images = [img for node in history[prompt_id]['outputs'].values() for img in node.get('images', [])]
            return [COMFY_OUTPUT / img.get('subfolder', '') / img['filename'] for img in images]
        time.sleep(2)


def video_graph(path, prefix):
    return {
        '1': {'class_type': 'VHS_LoadVideoPath', 'inputs': {'video': str(path), 'force_rate': 0, 'custom_width': 0, 'custom_height': 0,
                                                            'frame_load_cap': 0, 'skip_first_frames': 0, 'select_every_nth': 1}},
        '2': {'class_type': 'DownloadAndLoadDepthCrafterModel', 'inputs': {'enable_model_cpu_offload': False, 'enable_sequential_cpu_offload': False}},
        '3': {'class_type': 'DepthCrafter', 'inputs': {'depthcrafter_model': ['2', 0], 'images': ['1', 0], 'force_size': True,
                                                     'num_inference_steps': 10, 'guidance_scale': 1.2, 'window_size': 110, 'overlap': 25}},
        '4': {'class_type': 'SaveImage', 'inputs': {'images': ['3', 0], 'filename_prefix': prefix}},
    }


def image_graph(path, prefix):
    return {
        '1': {'class_type': 'VHS_LoadImagePath', 'inputs': {'image': str(path), 'custom_width': 0, 'custom_height': 0}},
        '2': {'class_type': 'DownloadAndLoadDepthAnythingV2Model', 'inputs': {'model': 'depth_anything_v2_vitl_fp32.safetensors'}},
        '3': {'class_type': 'DepthAnything_V2', 'inputs': {'da_model': ['2', 0], 'images': ['1', 0]}},
        '4': {'class_type': 'SaveImage', 'inputs': {'images': ['3', 0], 'filename_prefix': prefix}},
    }


# ComfyUI's built-in SAM3.1 nodes (comfy_extras.nodes_sam3): checkpoint + text conditioning.
SAM3_CHECKPOINT = 'sam3.1_multiplex_fp16.safetensors'


def sam3_base(prompt):
    return {
        '2': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM3_CHECKPOINT}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 1]}},
    }


def matte_video_graph(path, prefix, prompt):
    return {
        '1': {'class_type': 'VHS_LoadVideoPath', 'inputs': {'video': str(path), 'force_rate': 0, 'custom_width': 0, 'custom_height': 0,
                                                            'frame_load_cap': 0, 'skip_first_frames': 0, 'select_every_nth': 1}},
        **sam3_base(prompt),
        '4': {'class_type': 'SAM3_VideoTrack', 'inputs': {'images': ['1', 0], 'model': ['2', 0], 'conditioning': ['3', 0],
                                                          'detection_threshold': 0.4, 'max_objects': 6, 'detect_interval': 1}},
        '5': {'class_type': 'SAM3_TrackToMask', 'inputs': {'track_data': ['4', 0], 'object_indices': ''}},
        '6': {'class_type': 'MaskToImage', 'inputs': {'mask': ['5', 0]}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['6', 0], 'filename_prefix': prefix}},
    }


def matte_image_graph(path, prefix, prompt, threshold=0.4):
    return {
        '1': {'class_type': 'VHS_LoadImagePath', 'inputs': {'image': str(path), 'custom_width': 0, 'custom_height': 0}},
        **sam3_base(prompt),
        '4': {'class_type': 'SAM3_Detect', 'inputs': {'model': ['2', 0], 'image': ['1', 0], 'conditioning': ['3', 0], 'threshold': threshold,
                                                      'refine_iterations': 2, 'individual_masks': False}},
        '5': {'class_type': 'MaskToImage', 'inputs': {'mask': ['4', 0]}},
        '6': {'class_type': 'SaveImage', 'inputs': {'images': ['5', 0], 'filename_prefix': prefix}},
    }


def matte_points_graph(path, prefix, points):
    """SAM3 with click prompts: `points` is JSON [{"x": px, "y": px}, ...] in source pixels."""
    return {
        '1': {'class_type': 'VHS_LoadImagePath', 'inputs': {'image': str(path), 'custom_width': 0, 'custom_height': 0}},
        '2': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': SAM3_CHECKPOINT}},
        '4': {'class_type': 'SAM3_Detect', 'inputs': {'model': ['2', 0], 'image': ['1', 0], 'positive_coords': points, 'threshold': 0.3,
                                                      'refine_iterations': 2, 'individual_masks': False}},
        '5': {'class_type': 'MaskToImage', 'inputs': {'mask': ['4', 0]}},
        '6': {'class_type': 'SaveImage', 'inputs': {'images': ['5', 0], 'filename_prefix': prefix}},
    }


def main():
    kind, source, out_dir = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3])
    prompt = sys.argv[4] if len(sys.argv) > 4 else ''
    threshold = float(sys.argv[5]) if len(sys.argv) > 5 else 0.4
    prefix = f'portfolio_passes/{source.stem}_{int(time.time())}'
    graphs = {
        'video': lambda: video_graph(source, prefix),
        'image': lambda: image_graph(source, prefix),
        'matte-video': lambda: matte_video_graph(source, prefix, prompt),
        'matte-image': lambda: matte_image_graph(source, prefix, prompt, threshold),
        'matte-points': lambda: matte_points_graph(source, prefix, prompt),
    }
    started = time.time()
    files = sorted(run(graphs[kind](), prefix))
    out_dir.mkdir(parents=True, exist_ok=True)
    if kind in ('matte-image', 'matte-points') and len(files) > 1:
        # One mask per detection: merge them into a single matte.
        from PIL import Image, ImageChops
        merged = Image.open(files[0]).convert('L')
        for file in files[1:]:
            merged = ImageChops.lighter(merged, Image.open(file).convert('L'))
        merged.save(out_dir / '0000.png')
    else:
        for index, file in enumerate(files):
            shutil.copy(file, out_dir / f'{index:04d}.png')
    print(f'{source.name}: {len(files)} frame(s) in {time.time() - started:.0f}s -> {out_dir}')


if __name__ == '__main__':
    main()
