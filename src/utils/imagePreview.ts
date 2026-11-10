import imageSizes from '../data/image-sizes.json';

type ImagePresentation = {
  src: string;
  width?: number;
  height?: number;
};

const previews: Record<string, ImagePresentation> = {
  'assets/projects/fugi-visualizer/f1r-character-building-face.png': {
    src: 'assets/projects/fugi-visualizer/f1r-character-building-face.preview.webp', width: 1254, height: 1254
  },
  'assets/projects/fugi-visualizer/f1r-character-glitch.png': {
    src: 'assets/projects/fugi-visualizer/f1r-character-glitch.preview.webp', width: 1254, height: 1254
  },
  'assets/projects/fugi-visualizer/f1r-character-real.png': {
    src: 'assets/projects/fugi-visualizer/f1r-character-real.preview.webp', width: 1600, height: 900
  },
  'assets/projects/fugi-visualizer/f1r-highres-illustration-study-v003.png': {
    src: 'assets/projects/fugi-visualizer/f1r-highres-illustration-study-v003.preview.webp', width: 1600, height: 900
  },
  'assets/projects/fugi-visualizer/f1r-highres-illustration-study-v004.png': {
    src: 'assets/projects/fugi-visualizer/f1r-highres-illustration-study-v004.preview.webp', width: 1600, height: 900
  },
  'assets/projects/fugi-visualizer/fugi-visualizer-03-glitch.png': {
    src: 'assets/projects/fugi-visualizer/fugi-visualizer-03-glitch.preview.webp', width: 1582, height: 804
  },
  'assets/projects/fugi-visualizer/reference-tongue-in.png': {
    src: 'assets/projects/fugi-visualizer/reference-tongue-in.preview.webp', width: 1254, height: 1254
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/structure-hed.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/structure-hed.preview.webp', width: 1358, height: 1024
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/structure-depth.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/structure-depth.preview.webp', width: 1400, height: 1082
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/qwen-restyle.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/qwen-restyle.preview.webp', width: 1400, height: 1056
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/qwen-composite.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/qwen-composite.preview.webp', width: 1400, height: 1056
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/dwpose-guide.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/dwpose-guide.preview.webp', width: 1325, height: 1024
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/multi-character-composite.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/multi-character-composite.preview.webp', width: 1400, height: 1056
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/camera-low-angle.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/camera-low-angle.preview.webp', width: 1176, height: 888
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/comfyui-ltx2-pose-workflow.png': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/comfyui-ltx2-pose-workflow.preview.webp', width: 1400, height: 646
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/original-scene-frame.jpg': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/original-scene-frame.jpg', width: 1432, height: 1080
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-cover.jpg': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-cover.jpg', width: 1432, height: 1080
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-doorway.jpg': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-doorway.jpg', width: 1432, height: 1080
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-ensemble.jpg': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-ensemble.jpg', width: 1432, height: 1080
  },
  'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-presenter.jpg': {
    src: 'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-presenter.jpg', width: 1432, height: 1080
  }
};

// Pixel sizes of every other local image, written by scripts/build-image-sizes.mjs.
const sizes = imageSizes as unknown as Record<string, [number, number] | undefined>;

export function imagePresentation(path: string): ImagePresentation {
  const size = sizes[path];
  return previews[path] ?? (size ? { src: path, width: size[0], height: size[1] } : { src: path });
}
