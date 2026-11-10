#!/usr/bin/env node
// Records the pixel size of every local image the project pages show (src/data/image-sizes.json),
// so <img> tags can reserve their space before the file arrives. Run after adding images.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (file) => JSON.parse(fs.readFileSync(path.join(root, file), 'utf8'));
const projects = [...read('content/manual-projects.json'), ...read('src/data/artstation-projects.json')];
const markdown = ['content/articles', 'content/pages'].flatMap((folder) => fs.readdirSync(path.join(root, folder))
  .filter((file) => file.endsWith('.md')).map((file) => fs.readFileSync(path.join(root, folder, file), 'utf8')));

const images = new Set();
const collect = (text) => {
  for (const match of String(text).matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) images.add(match[1]);
};
for (const project of projects) {
  for (const image of [project.cover, ...(project.gallery ?? [])]) if (image) images.add(image);
  collect(Array.isArray(project.body) ? project.body.join('\n') : project.body ?? '');
}
markdown.forEach(collect);

const sizes = {};
for (const image of [...images].sort()) {
  const file = path.join(root, 'public', image);
  if (/^https?:/.test(image) || !fs.existsSync(file)) continue;
  const result = spawnSync('magick', ['identify', '-format', '%w %h', `${file}[0]`]);
  const [width, height] = result.stdout.toString().trim().split(' ').map(Number);
  if (width && height) sizes[image] = [width, height];
}

fs.writeFileSync(path.join(root, 'src/data/image-sizes.json'), `${JSON.stringify(sizes, null, 2)}\n`);
console.log(`image sizes: ${Object.keys(sizes).length} of ${images.size} images`);
