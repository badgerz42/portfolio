import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { asString, readMarkdownDocuments, slugify } from './lib/content.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const siteUrl = (process.env.SITE_URL || 'https://vladmaftei.com').replace(/\/$/, '');
const defaultImage = 'assets/share/vladmaftei-share.jpg';
const baseHtml = await fs.readFile(path.join(dist, 'index.html'), 'utf8');
const importedProjects = JSON.parse(await fs.readFile(path.join(root, 'src/data/artstation-projects.json'), 'utf8'));
const manualProjects = JSON.parse(await fs.readFile(path.join(root, 'content/manual-projects.json'), 'utf8'));
const overrides = JSON.parse(await fs.readFile(path.join(root, 'content/project-overrides.json'), 'utf8'));
// Mirror src/data/projects.ts: curated overrides win over imported/manual fields.
const projects = (importedProjects.length > 0 ? importedProjects : manualProjects).map((project) => ({
  ...project,
  ...(overrides[project.slug || slugify(project.title)] ?? {})
}));
const articles = await readMarkdownDocuments(root, 'content/articles', 'article');
const pages = await readMarkdownDocuments(root, 'content/pages', 'page');

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function absoluteAsset(asset = defaultImage) {
  if (/^https?:\/\//i.test(asset)) return asset;
  return `${siteUrl}/${String(asset).replace(/^\//, '')}`;
}

function routeMeta({ title, description, route, canonicalRoute = route, image = defaultImage, type = 'website' }) {
  const canonical = `${siteUrl}/${canonicalRoute ? `${canonicalRoute.replace(/^\/+|\/+$/g, '')}/` : ''}`;
  const safeTitle = escapeHtml(title);
  const safeDescription = escapeHtml(description);
  const safeImage = escapeHtml(absoluteAsset(image));
  const safeCanonical = escapeHtml(canonical);

  return `<!-- route-meta:start -->
    <meta name="description" content="${safeDescription}" />
    <link rel="canonical" href="${safeCanonical}" />
    <meta property="og:title" content="${safeTitle}" />
    <meta property="og:description" content="${safeDescription}" />
    <meta property="og:type" content="${type}" />
    <meta property="og:url" content="${safeCanonical}" />
    <meta property="og:image" content="${safeImage}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${safeTitle}" />
    <meta name="twitter:description" content="${safeDescription}" />
    <meta name="twitter:image" content="${safeImage}" />
    <title>${safeTitle}</title>
    <!-- route-meta:end -->`;
}

const person = {
  '@type': 'Person',
  name: 'Vlad Maftei',
  url: `${siteUrl}/`,
  jobTitle: '3D generalist / VFX / AI video artist',
  address: { '@type': 'PostalAddress', addressLocality: 'Bucharest', addressCountry: 'RO' },
  sameAs: ['https://vladmaftei.artstation.com/', 'https://www.linkedin.com/in/vladmaftei/', 'https://www.instagram.com/_vladski_/', 'https://x.com/Badgerz']
};

// Structured data so search results can show who made what.
function jsonLd(data) {
  return `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', ...data }).replace(/</g, '\\u003c')}</script>`;
}

const inline = (text) => escapeHtml(text).replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');

// Article markdown (the subset ContentRenderer understands) as plain semantic HTML.
function bodyHtml(body) {
  const lines = (Array.isArray(body) ? body.join('\n') : body || '').split(/\r?\n/);
  const out = [];
  let list = [];
  const flush = () => {
    if (list.length) out.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join('')}</ul>`);
    list = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    const item = line.match(/^[-*]\s+(.+)$/);
    if (item) { list.push(item[1]); continue; }
    flush();
    if (!line || line.startsWith('::embed')) continue;
    const heading = line.match(/^(#{2,4})\s+(.+)$/);
    const image = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    const video = line.match(/^::video\[([^\]]+)\]\(([^)]+)\)$/);
    if (heading) out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`);
    else if (image) out.push(`<figure><img src="/${escapeHtml(image[2].replace(/^\//, ''))}" alt="${escapeHtml(image[1])}" loading="lazy" /><figcaption>${escapeHtml(image[1])}</figcaption></figure>`);
    else if (video) out.push(`<p><a href="${/^https?:/.test(video[2]) ? escapeHtml(video[2]) : `/${escapeHtml(video[2])}`}">Video: ${escapeHtml(video[1])}</a></p>`);
    else out.push(`<p>${inline(line)}</p>`);
  }
  flush();
  return out.join('\n');
}

// The app replaces this on mount; it exists so the page has real text without JavaScript.
function prerender(content) {
  return `<div class="prerender"><p><a href="/">Vlad Maftei</a> — VFX / 3D / AI</p>\n${content}\n<p><a href="/#work">All work</a> · <a href="/pages/about/">About</a> · <a href="mailto:vladmaftei@gmail.com">vladmaftei@gmail.com</a></p></div>`;
}

function renderRoute(metadata) {
  return baseHtml
    .replace(/<!-- route-meta:start -->[\s\S]*?<!-- route-meta:end -->/, `${routeMeta(metadata)}\n    ${jsonLd(metadata.structured ?? { '@type': 'WebPage', name: metadata.title, author: person })}`)
    .replace('<!-- prerender -->', () => (metadata.content ? prerender(metadata.content) : ''));
}

async function writeRoute(metadata) {
  const routeDirectory = path.join(dist, metadata.route);
  await fs.mkdir(routeDirectory, { recursive: true });
  await fs.writeFile(path.join(routeDirectory, 'index.html'), renderRoute(metadata));
}

const rootMetadata = {
  title: 'Vlad Maftei — VFX / 3D / AI',
  description: 'Vlad Maftei portfolio: cinematic visual work across VFX, 3D, creature animation, procedural systems, product imagery and AI-driven video.',
  route: '',
  image: defaultImage,
  type: 'website'
};

const projectRoute = (project) => `projects/${project.slug || slugify(project.title)}`;
// Newest first, like the homepage.
const byDate = [...projects].sort((a, b) => (b.date ?? `${b.year ?? '0000'}-00-00`).localeCompare(a.date ?? `${a.year ?? '0000'}-00-00`));

rootMetadata.structured = { '@type': 'ProfilePage', name: rootMetadata.title, url: `${siteUrl}/`, mainEntity: person };
rootMetadata.content = `<h1>Vlad Maftei</h1>
<p>3D generalist / VFX / AI video — Bucharest. Available for freelance, studio and remote work.</p>
<p>I make cinematic images with 3D, simulation and generative video: creature animation and fur, product CGI and digital humans, LTX film sequences and point-cloud music videos.</p>
<h2>Selected work</h2>
<ul>${byDate.map((project) => `<li><a href="/${projectRoute(project)}/">${escapeHtml(project.title)}</a>${project.year ? ` (${escapeHtml(project.year)})` : ''}: ${escapeHtml(project.description ?? '')}</li>`).join('\n')}</ul>`;

await fs.writeFile(path.join(dist, 'index.html'), renderRoute(rootMetadata));
await fs.writeFile(path.join(dist, '404.html'), renderRoute({ ...rootMetadata, content: '' }));

const routeEntries = projects.map((project) => ({
  title: `${project.title} — Vlad Maftei`,
  description: project.description || `${project.title}, a portfolio project by Vlad Maftei.`,
  route: projectRoute(project),
  image: project.cover || defaultImage,
  type: 'article',
  structured: {
    '@type': 'CreativeWork',
    name: project.title,
    description: project.description,
    url: `${siteUrl}/${projectRoute(project)}/`,
    image: absoluteAsset(project.cover),
    ...(project.date ? { datePublished: project.date } : project.year ? { dateCreated: String(project.year) } : {}),
    keywords: [...(project.tags ?? []), ...(project.tools ?? [])].join(', '),
    creator: person
  },
  content: `<h1>${escapeHtml(project.title)}</h1>
<p>${escapeHtml([project.year, project.role].filter(Boolean).join(' — '))}</p>
<p>${escapeHtml(project.description ?? '')}</p>
${project.tools?.length ? `<p>Tools: ${escapeHtml(project.tools.join(', '))}</p>` : ''}
${(project.videos ?? []).map((video) => `<p><a href="${/^https?:/.test(video.url) ? escapeHtml(video.url) : `/${escapeHtml(video.url)}`}">Video: ${escapeHtml(video.title ?? project.title)}</a></p>`).join('\n')}
${bodyHtml(project.body)}`
}));

for (const document of [...articles, ...pages]) {
  if (asString(document.attributes.status) === 'draft') continue;
  const title = asString(document.attributes.title) || document.slug.replace(/-/g, ' ');
  routeEntries.push({
    title: `${title} — Vlad Maftei`,
    description: asString(document.attributes.excerpt) || `${title} — Vlad Maftei.`,
    route: `${document.kind === 'article' ? 'articles' : 'pages'}/${document.slug}`,
    image: asString(document.attributes.cover) || defaultImage,
    type: document.kind === 'article' ? 'article' : 'website',
    content: `<h1>${escapeHtml(title)}</h1>\n${bodyHtml(document.body)}`
  });
}

// Old slugs of merged projects keep working and point search engines at the surviving page.
const aliasEntries = projects.flatMap((project) => (project.aliases ?? []).map((alias) => ({
  ...routeEntries.find((entry) => entry.route === `projects/${project.slug || slugify(project.title)}`),
  route: `projects/${alias}`,
  canonicalRoute: `projects/${project.slug || slugify(project.title)}`
})));

for (const route of [...routeEntries, ...aliasEntries]) await writeRoute(route);

const sitemapRoutes = ['', ...routeEntries.map((entry) => `${entry.route}/`)];
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemapRoutes.map((route) => `  <url><loc>${siteUrl}/${route}</loc></url>`).join('\n')}
</urlset>
`;

await fs.writeFile(path.join(dist, 'sitemap.xml'), sitemap);
console.log(`Generated ${routeEntries.length + 1} static route entr${routeEntries.length === 0 ? 'y' : 'ies'} and sitemap.xml.`);
