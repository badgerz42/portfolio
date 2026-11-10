import { useEffect, useRef, useState } from 'react';
import type { PortfolioProject, ProjectKind } from '../data/projects';
import { projectHref } from '../utils/routes';
import { projectLoop, projectThumb, viewTransitionName } from '../utils/projectMedia';
import { ProjectThumb } from './ProjectThumb';

const filters: Array<{ kind: ProjectKind | 'all'; label: string }> = [
  { kind: 'all', label: 'all' },
  { kind: 'ai', label: 'ai' },
  { kind: '3d', label: '3d' },
  { kind: 'vfx', label: 'vfx' },
  { kind: 'product', label: 'product' },
  { kind: 'realtime', label: 'realtime' }
];

const slugOf = (project: PortfolioProject) => project.slug ?? '';

// Tile shapes follow position (not project) so the grid stays balanced whatever the order.
// Each pattern fills whole rows of the four-column grid, so no tile is left alone on a last row.
const tilePattern = ['lead', 'tall', 'std', 'std', 'wide', 'std', 'std'] as const;
const tilePatternOfEight = ['lead', 'tall', 'std', 'std', 'std', 'std', 'lead', 'wide'] as const;
const tileAt = (index: number, count: number) => {
  const pattern = count % tilePattern.length === 1 && index >= count - tilePatternOfEight.length ? tilePatternOfEight : tilePattern;
  const offset = pattern === tilePatternOfEight ? count - tilePatternOfEight.length : 0;
  return pattern[(index - offset) % pattern.length];
};
const matches = (project: PortfolioProject, filter: ProjectKind | 'all') => filter === 'all' || Boolean(project.kind?.includes(filter));
const kindLabel = (project: PortfolioProject) => (project.kind ?? []).filter((kind) => kind !== 'code').join(' / ').toUpperCase();

const canHover = () => window.matchMedia('(hover: hover) and (pointer: fine)').matches;
const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Silent loop that downloads on first hover (or first time in view on touch screens), then plays while active. */
function HoverLoop({ slug, active }: { slug: string; active: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [inView, setInView] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [touchMode] = useState(() => !canHover());
  const [reducedMotion] = useState(prefersReducedMotion);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !touchMode || reducedMotion) return undefined;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.intersectionRatio >= 0.6), { threshold: [0, 0.6, 1] });
    observer.observe(video);
    return () => observer.disconnect();
  }, [touchMode, reducedMotion]);

  const wanted = !reducedMotion && (active || (touchMode && inView));

  useEffect(() => {
    if (wanted) setLoaded(true);
  }, [wanted]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !loaded) return;
    if (wanted) void video.play().catch(() => undefined);
    else video.pause();
  }, [wanted, loaded]);

  return (
    <video
      ref={videoRef}
      className={`work-loop${wanted && loaded ? ' is-playing' : ''}`}
      src={loaded ? projectLoop(slug) : undefined}
      muted
      loop
      playsInline
      preload="none"
      aria-hidden="true"
      tabIndex={-1}
    />
  );
}

function WorkTile({ project, index, count, dimmed }: { project: PortfolioProject; index: number; count: number; dimmed: boolean }) {
  const [active, setActive] = useState(false);
  const slug = slugOf(project);
  const tile = tileAt(index, count);
  const lead = tile === 'lead';

  return (
    <article
      className={`work-tile work-tile--${tile}${dimmed ? ' is-dimmed' : ''}`}
      data-reveal
      onPointerEnter={() => setActive(true)}
      onPointerLeave={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={() => setActive(false)}
    >
      <a href={projectHref(slug)} tabIndex={dimmed ? -1 : undefined} aria-describedby={`work-desc-${slug}`}>
        <div className="work-tile__media" style={{ viewTransitionName: viewTransitionName(slug) }}>
          <ProjectThumb
            slug={slug}
            alt={`${project.title} artwork`}
            sizes={lead ? '(max-width: 760px) 100vw, 50vw' : '(max-width: 760px) 100vw, 25vw'}
            eager={lead}
            focus={project.coverFocus}
          />
          <HoverLoop slug={slug} active={active} />
        </div>
        <div className="work-tile__info">
          <span className="work-tile__index">_{String(index + 1).padStart(2, '0')}</span>
          <h3>{project.title}</h3>
          <p id={`work-desc-${slug}`}>{project.description}</p>
          <small>{[project.year, kindLabel(project)].filter(Boolean).join(' / ')}</small>
        </div>
      </a>
    </article>
  );
}

/** Terminal-style `ls -la` list with an image preview that trails the cursor. */
function ArchiveList({ projects, filter, startIndex }: { projects: PortfolioProject[]; filter: ProjectKind | 'all'; startIndex: number }) {
  const previewRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    const preview = previewRef.current;
    if (!preview || !canHover()) return undefined;
    let frame = 0;
    const position = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const onMove = (event: PointerEvent) => {
      position.targetX = event.clientX;
      position.targetY = event.clientY;
    };
    const tick = () => {
      position.x += (position.targetX - position.x) * 0.18;
      position.y += (position.targetY - position.y) * 0.18;
      preview.style.transform = `translate3d(${position.x + 28}px, ${position.y - 90}px, 0)`;
      frame = window.requestAnimationFrame(tick);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    frame = window.requestAnimationFrame(tick);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const visible = projects.filter((project) => matches(project, filter));

  return (
    <div className="archive" data-reveal>
      <div className="archive__head" aria-hidden="true">
        <span>$ ls -la ./archive</span>
        <span>{visible.length} entr{visible.length === 1 ? 'y' : 'ies'}</span>
      </div>
      <ul className="archive__list" onPointerLeave={() => setHovered(null)}>
        {projects.map((project, index) => {
          const slug = slugOf(project);
          const hidden = !matches(project, filter);
          return (
            <li key={slug} hidden={hidden}>
              <a
                className="archive__row"
                href={projectHref(slug)}
                onPointerEnter={() => setHovered(slug)}
                onFocus={() => setHovered(slug)}
                onBlur={() => setHovered(null)}
              >
                <span className="archive__index">_{String(startIndex + index + 1).padStart(2, '0')}</span>
                <span className="archive__year">{project.year ?? '----'}</span>
                <span className="archive__thumb" aria-hidden="true">
                  <img src={projectThumb(slug).fallback} alt="" loading="lazy" decoding="async" />
                </span>
                <strong className="archive__title">{project.title}</strong>
                <span className="archive__role">{project.role}</span>
                <span className="archive__tools">{project.tools?.slice(0, 3).join(', ')}</span>
                <span className="archive__arrow" aria-hidden="true">-&gt;</span>
              </a>
            </li>
          );
        })}
      </ul>
      <div className={`archive__preview${hovered ? ' is-visible' : ''}`} ref={previewRef} aria-hidden="true">
        {projects.map((project) => {
          const slug = slugOf(project);
          return (
            <div className={`archive__preview-frame${hovered === slug ? ' is-active' : ''}`} key={slug}>
              <img src={projectThumb(slug).fallback} alt="" loading="lazy" decoding="async" />
              {hovered === slug ? <video src={projectLoop(slug)} muted loop playsInline autoPlay /> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function WorkShowcase({ featured, archive }: { featured: PortfolioProject[]; archive: PortfolioProject[] }) {
  const [filter, setFilter] = useState<ProjectKind | 'all'>('all');
  const matchingCount = [...featured, ...archive].filter((project) => matches(project, filter)).length;

  return (
    <div className="work-showcase">
      <div className="work-filters" role="group" aria-label="Filter projects by discipline">
        <span className="work-filters__prompt" aria-hidden="true">$ work</span>
        {filters.map((item) => (
          <button
            type="button"
            key={item.kind}
            aria-pressed={filter === item.kind}
            onClick={() => setFilter(item.kind)}
          >
            --{item.label}
          </button>
        ))}
        <span className="work-filters__count" aria-live="polite">{matchingCount} match{matchingCount === 1 ? '' : 'es'}</span>
      </div>

      <div className="work-bento">
        {featured.map((project, index) => (
          <WorkTile project={project} index={index} count={featured.length} dimmed={!matches(project, filter)} key={slugOf(project)} />
        ))}
      </div>

      {archive.length > 0 ? <ArchiveList projects={archive} filter={filter} startIndex={featured.length} /> : null}
    </div>
  );
}
