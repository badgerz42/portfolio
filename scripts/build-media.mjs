// Generates the optimized media the site uses: responsive AVIF/WebP thumbnails,
// short silent hover loops per project, and the homepage hero reel.
//
// Requires ffmpeg (libx264) and ImageMagick 7 (`magick`) on PATH.
// Outputs are committed under public/assets/generated/ so CI does not need them.
//
//   node scripts/build-media.mjs            # build everything missing
//   node scripts/build-media.mjs --force    # rebuild everything
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pub = path.join(root, 'public');
const outDir = path.join(pub, 'assets/generated');
const force = process.argv.includes('--force');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vm-media-'));
const projects = JSON.parse(fs.readFileSync(path.join(root, 'content/manual-projects.json'), 'utf8'));
const overrides = JSON.parse(fs.readFileSync(path.join(root, 'content/project-overrides.json'), 'utf8'));

const FPS = 30;
const NOTLD = 'assets/projects/night-of-the-living-dead-ltx-contest/night-of-the-living-dead-final.mp4';
const XP = 'assets/artstation/xparticles-challenge-2018-animation-tests-and-explorations';
const FUGI = 'assets/projects/fugi-visualizer';
const F1R_LIVE = 'assets/projects/f1r-live-video/f1r-live-final.mp4';
const DARK_FOREST = 'assets/projects/dark-forest/dark-forest-final.mp4';
const DARK_FOREST_INK = 'assets/projects/dark-forest/look-dev-ink-edit.mp4';

function run(cmd, args) {
  const result = spawnSync(cmd, args, { stdio: ['ignore', 'ignore', 'pipe'] });
  if (result.status !== 0) {
    throw new Error(`${cmd} ${args.join(' ')}\n${result.stderr?.toString().slice(-2000)}`);
  }
}

const abs = (asset) => path.join(pub, asset);
const needs = (file) => force || !fs.existsSync(file);
const ensureDir = (file) => fs.mkdirSync(path.dirname(file), { recursive: true });

// Prefer the lighter .preview.webp next to a PNG when it exists.
function bestSource(asset) {
  const preview = asset.replace(/\.png$/i, '.preview.webp');
  return preview !== asset && fs.existsSync(abs(preview)) ? preview : asset;
}

/* ---------- thumbnails ---------- */

// Covers exported with baked-in letterbox bars get them trimmed off.
const letterboxed = new Set(['quixel-mixer-contest']);

function thumbnails(slug, cover) {
  for (const width of [640, 1280]) {
    for (const format of ['avif', 'webp']) {
      const target = path.join(outDir, 'thumbs', `${slug}-${width}.${format}`);
      if (!needs(target)) continue;
      ensureDir(target);
      const trim = letterboxed.has(slug) ? ['-fuzz', '4%', '-trim', '+repage'] : [];
      run('magick', [abs(bestSource(cover)), ...trim, '-resize', `${width}x>`, '-strip', '-quality', format === 'avif' ? '52' : '74', target]);
    }
  }
}

/* ---------- video segments ---------- */

// `focus` reframes a clip: zoom in and place a point (0-1 fractions of the source) at
// `at` (0-1 of the output width, default centre). `atSmall` overrides it for the phone
// reel, whose portrait hero crop keeps only the middle of the frame.
function clipSegment(source, start, duration, width, height, file, focus) {
  const zoom = focus?.zoom ?? 1;
  const at = (height < 720 ? focus?.atSmall : undefined) ?? focus?.at ?? 0.5;
  const x = focus ? `min(max(iw*${focus.x}-ow*${at}\\,0)\\,iw-ow)` : '(iw-ow)/2';
  const y = focus ? `min(max(ih*${focus.y}-oh/2\\,0)\\,ih-oh)` : '(ih-oh)/2';
  const scaled = `scale=${Math.round(width * zoom)}:${Math.round(height * zoom)}:force_original_aspect_ratio=increase:flags=lanczos`;
  run('ffmpeg', ['-v', 'error', '-y', '-ss', String(start), '-t', String(duration), '-i', abs(source),
    '-an', '-vf', `${scaled},crop=${width}:${height}:${x}:${y},fps=${FPS},format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', file]);
}

// Slow push-in on a still; direction alternates so consecutive stills don't feel identical.
function stillSegment(source, duration, width, height, file, variant = 0) {
  const frames = Math.round(duration * FPS);
  const zoom = `1.02+0.07*on/${frames}`;
  const x = variant % 2 === 0 ? 'iw/2-(iw/zoom/2)' : `(iw-iw/zoom)*(0.35+0.3*on/${frames})`;
  run('ffmpeg', ['-v', 'error', '-y', '-i', abs(bestSource(source)), '-an',
    '-vf', `scale=${width * 2}:${height * 2}:force_original_aspect_ratio=increase,crop=${width * 2}:${height * 2},zoompan=z='${zoom}':x='${x}':y='ih/2-(ih/zoom/2)':d=${frames}:s=${width}x${height}:fps=${FPS},format=yuv420p`,
    '-frames:v', String(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', file]);
}

function renderSegments(segments, width, height, key) {
  return segments.map((segment, index) => {
    const file = path.join(tmp, `${key}-${width}-${index}.mp4`);
    if (segment.clip) clipSegment(segment.clip, segment.start, segment.duration, width, height, file, segment.focus);
    else stillSegment(segment.still, segment.duration, width, height, file, index);
    return file;
  });
}

function concatEncode(files, target, crf) {
  const list = path.join(tmp, `${path.basename(target)}.txt`);
  fs.writeFileSync(list, files.map((file) => `file '${file}'`).join('\n'));
  ensureDir(target);
  run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-an',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', String(crf), '-profile:v', 'high', '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart', target]);
}

function poster(video, target, at = 0.4) {
  run('ffmpeg', ['-v', 'error', '-y', '-ss', String(at), '-i', video, '-frames:v', '1', '-q:v', '4', target]);
}

/* ---------- hover loops ---------- */

const gallerySlides = (project, count = 4) => {
  const images = [project.cover, ...(project.gallery ?? [])]
    .filter((image, index, list) => /\.(jpe?g|png|webp)$/i.test(image) && list.indexOf(image) === index)
    .slice(0, count);
  const each = images.length > 1 ? 1.1 : 4;
  return images.map((still) => ({ still, duration: each }));
};

const customLoops = {
  'polar-bear-walk': [{ clip: 'assets/projects/polar-bear-walk/polar-bear-final.mp4', start: 2, duration: 4.5 }],
  'f1r-live-video': [{ clip: F1R_LIVE, start: 158, duration: 4.5 }],
  'dark-forest': [{ clip: DARK_FOREST, start: 9, duration: 4.5 }],
  'night-of-the-living-dead-ltx-contest': [{ clip: NOTLD, start: 64.2, duration: 4 }],
  'x-particles-challenge-2018': [{ clip: `${XP}/06-xparticles-animation-test-camera27.mp4`, start: 0.2, duration: 4.2 }],
  'fugi-visualizer': [
    { still: `${FUGI}/reference-tongue-in.png`, duration: 1.1 },
    { still: `${FUGI}/f1r-character-glitch.png`, duration: 1.1 },
    { still: `${FUGI}/fugi-visualizer-03-glitch.png`, duration: 1.1 },
    { still: `${FUGI}/f1r-character-real.png`, duration: 1.1 }
  ]
};

/* ---------- hero reel ---------- */

const coverOf = (slug) => projects.find((project) => project.slug === slug)?.cover;
// `slug` ties each shot to its project so the site can caption what's on screen (reel.json).
const reel = [
  // Only recent work: 2025-2026, plus Trips (2024).
  { slug: 'f1r-live-video', tools: ['LTX-2.3', 'Pi3X point cloud'], clip: F1R_LIVE, start: 149, duration: 1.8 },
  { slug: 'night-of-the-living-dead-ltx-contest', clip: NOTLD, start: 30.4, duration: 1.8 },
  // Reframed so the boy and his lantern sit in the middle of the hero's open area, clear of the title.
  { slug: 'dark-forest', tools: ['Hunyuan3D', 'Kimodo', 'Blender'], clip: DARK_FOREST, start: 10, duration: 1.8, focus: { x: 0.35, y: 0.6, zoom: 1.65, at: 0.58, atSmall: 0.5 } },
  { slug: 'daft-punk-cover-art', still: coverOf('daft-punk-cover-art'), duration: 1.4 },
  { slug: 'night-of-the-living-dead-ltx-contest', clip: NOTLD, start: 66, duration: 1.8 },
  { slug: 'f1r-live-video', tools: ['LTX-2.3', 'Pi3X point cloud'], clip: F1R_LIVE, start: 166, duration: 1.8 },
  { slug: 'dark-forest', tools: ['MiniMax H3', 'DepthCrafter'], clip: DARK_FOREST_INK, start: 12, duration: 1.5 },
  { slug: 'cat-walkman', still: coverOf('cat-walkman'), duration: 1.4 },
  { slug: 'trips', tools: ['Flux', 'Runway'], still: 'assets/artstation/trips/04-vlx-maftei-landscapes-04.jpg', duration: 1.5 },
  { slug: 'night-of-the-living-dead-ltx-contest', clip: NOTLD, start: 20, duration: 1.6 },
  { slug: 'fugi-visualizer', tools: ['Codex', 'WebGL'], still: `${FUGI}/f1r-character-glitch.png`, duration: 1.4 },
  { slug: 'f1r-live-video', tools: ['LTX-2.3', 'Pi3X point cloud'], clip: F1R_LIVE, start: 184, duration: 1.6 },
  { slug: 'night-of-the-living-dead-ltx-contest', clip: NOTLD, start: 100, duration: 2 },
  { slug: 'trips', tools: ['Flux', 'Runway'], still: 'assets/artstation/trips/07-vlx-maftei-landscapes-07.jpg', duration: 1.5 },
  { slug: 'fugi-visualizer', tools: ['Codex', 'WebGL'], still: `${FUGI}/reference-tongue-in.png`, duration: 1.4 }
];

function probeDuration(file) {
  const result = spawnSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]);
  return Number.parseFloat(result.stdout.toString()) || 0;
}

// Shot timings + captions for the hero's decrypt band, measured from the rendered segments
// so frame rounding can't make the captions drift.
function writeReelManifest(segmentFiles) {
  const target = path.join(outDir, 'reel', 'reel.json');
  let time = 0;
  const shots = reel.map((segment, index) => {
    const duration = probeDuration(segmentFiles[index]);
    const project = { ...projects.find((item) => item.slug === segment.slug), ...(overrides[segment.slug] ?? {}) };
    const shot = {
      start: +time.toFixed(3),
      end: +(time + duration).toFixed(3),
      slug: segment.slug,
      title: project.title,
      tools: segment.tools ?? (project.tools ?? []).slice(0, 2)
    };
    time += duration;
    return shot;
  });
  ensureDir(target);
  fs.writeFileSync(target, `${JSON.stringify({ duration: +time.toFixed(3), shots }, null, 2)}\n`);
}

/* ---------- run ---------- */

const breakdownFrames = [
  'assets/projects/night-of-the-living-dead-ltx-contest/original-scene-frame.jpg',
  'assets/projects/night-of-the-living-dead-ltx-contest/final-frame-cover.jpg'
];

try {
  for (const project of projects) {
    thumbnails(project.slug, project.cover);

    const loop = path.join(outDir, 'loops', `${project.slug}.mp4`);
    if (needs(loop)) {
      const segments = customLoops[project.slug] ?? gallerySlides({ ...project, ...(overrides[project.slug] ?? {}) });
      concatEncode(renderSegments(segments, 640, 360, project.slug), loop, 30);
      console.log('loop', path.relative(root, loop), `${Math.round(fs.statSync(loop).size / 1024)} KB`);
    }
  }

  for (const frame of breakdownFrames) {
    const target = abs(frame.replace(/\.jpg$/, '.preview.webp'));
    if (needs(target)) run('magick', [abs(frame), '-resize', '1400x>', '-strip', '-quality', '78', target]);
  }

  for (const [width, height, crf] of [[1280, 720, 30], [854, 480, 31]]) {
    const target = path.join(outDir, 'reel', `reel-${height}.mp4`);
    if (!needs(target)) continue;
    const segmentFiles = renderSegments(reel, width, height, 'reel');
    if (height === 720) writeReelManifest(segmentFiles);
    concatEncode(segmentFiles, target, crf);
    console.log('reel', path.relative(root, target), `${Math.round(fs.statSync(target).size / 1024)} KB`);
    if (height === 720) poster(target, path.join(outDir, 'reel', 'reel-poster.jpg'));
  }
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
