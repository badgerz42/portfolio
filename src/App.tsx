import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArticleIndex } from './components/ArticleIndex';
import { AsciiBunny } from './components/AsciiBunny';
import { BreakdownSlider } from './components/BreakdownSlider';
import { ContactBlock } from './components/ContactBlock';
import { ContentPage } from './components/ContentPage';
import { GlitchText } from './components/GlitchText';
import { HeroReel, type ReelShot } from './components/HeroReel';
import { NowPlaying } from './components/NowPlaying';
import { HeroTerminalLine } from './components/HeroTerminalLine';
import { NotFoundPage } from './components/NotFoundPage';
import { ProjectDetailPage } from './components/ProjectDetailPage';
import { SocialIcons } from './components/SocialIcons';
import { WorkShowcase } from './components/WorkShowcase';
import { articles, featuredArticle, getArticle, getPage, pages } from './data/content';
import { archiveProjects, featuredProjects, getProject, projects } from './data/projects';
import { availability, contactEmail, profileFacts } from './data/profile';
import { useReveal } from './hooks/useReveal';
import { useSmoothScroll } from './hooks/useSmoothScroll';
import { assetPath } from './utils/assetPath';
import { articleHref, homeHref, homeSectionHref, pageHref, pathWithoutBase, projectHref } from './utils/routes';

type Route =
  | { type: 'home'; section?: HomeSection }
  | { type: 'article'; slug: string }
  | { type: 'page'; slug: string }
  | { type: 'project'; slug: string };

type ActiveBunny = 'hero' | 'work';
type HomeSection = 'work' | 'process' | 'articles' | 'about' | 'contact';

const homeSections: HomeSection[] = ['work', 'process', 'articles', 'about', 'contact'];

const navLinks: Array<{ href: string; label: string; section: HomeSection }> = [
  { href: homeSectionHref('work'), label: 'Work', section: 'work' },
  { href: homeSectionHref('process'), label: 'Process', section: 'process' },
  ...(articles.length > 0 ? [{ href: homeSectionHref('articles'), label: 'Articles', section: 'articles' as HomeSection }] : []),
  { href: pageHref('about'), label: 'About', section: 'about' },
  { href: homeSectionHref('contact'), label: 'Contact', section: 'contact' }
];


const processSteps = [
  { title: 'Concept / Reference', text: 'Reference pulls, boards and timing locked to picture and sound before anything renders.' },
  { title: 'Structure', text: '3D blockouts, pose and depth guides, so generated passes follow the camera and the performance.' },
  { title: 'Generate / Simulate', text: 'ComfyUI graphs, LTX-2, X-Particles and cloth sims, iterated as short tests instead of long gambles.' },
  { title: 'Comp / Deliver', text: 'Cleanup, grade and conform back into the original edit, delivered as masters.' }
];

function parseRouteValue(cleaned: string): Route {
  if (cleaned.startsWith('articles/')) return { type: 'article', slug: cleaned.replace('articles/', '') };
  if (cleaned.startsWith('pages/')) return { type: 'page', slug: cleaned.replace('pages/', '') };
  if (cleaned.startsWith('projects/')) return { type: 'project', slug: cleaned.replace('projects/', '') };
  const section = homeSections.find((candidate) => candidate === cleaned);
  return { type: 'home', section };
}

function parseLocationRoute(): Route {
  const legacyHash = window.location.hash.match(/^#\/(.+)/);
  if (legacyHash) return parseRouteValue(legacyHash[1].replace(/^\/+|\/+$/g, ''));

  const pathRoute = parseRouteValue(pathWithoutBase(window.location.pathname));
  if (pathRoute.type !== 'home') return pathRoute;

  const section = window.location.hash.replace(/^#/, '');
  return parseRouteValue(section);
}

function useLocationRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseLocationRoute());

  useEffect(() => {
    const onLocationChange = () => setRoute(parseLocationRoute());
    window.addEventListener('hashchange', onLocationChange);
    window.addEventListener('popstate', onLocationChange);
    return () => {
      window.removeEventListener('hashchange', onLocationChange);
      window.removeEventListener('popstate', onLocationChange);
    };
  }, []);

  return route;
}

function useHomeSectionScroll(route: Route) {
  useEffect(() => {
    if (route.type !== 'home') return undefined;

    const frame = window.requestAnimationFrame(() => {
      if (route.section) {
        document.getElementById(route.section)?.scrollIntoView({ block: 'start', behavior: 'auto' });
        return;
      }

      window.scrollTo({ top: 0, behavior: 'auto' });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [route]);
}

type RouteMetadata = {
  title: string;
  description: string;
  image: string;
  canonicalPath: string;
  type: 'website' | 'article';
};

function setMetaContent(selector: string, attribute: 'name' | 'property', key: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(selector);
  if (!element) {
    element = document.createElement('meta');
    element.setAttribute(attribute, key);
    document.head.appendChild(element);
  }
  element.content = content;
}

function useRouteMetadata(metadata: RouteMetadata) {
  useEffect(() => {
    const canonicalUrl = new URL(metadata.canonicalPath, window.location.origin).href;
    const imageUrl = new URL(assetPath(metadata.image), window.location.origin).href;
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');

    if (!canonical) {
      canonical = document.createElement('link');
      canonical.rel = 'canonical';
      document.head.appendChild(canonical);
    }

    document.title = metadata.title;
    canonical.href = canonicalUrl;
    setMetaContent('meta[name="description"]', 'name', 'description', metadata.description);
    setMetaContent('meta[property="og:title"]', 'property', 'og:title', metadata.title);
    setMetaContent('meta[property="og:description"]', 'property', 'og:description', metadata.description);
    setMetaContent('meta[property="og:type"]', 'property', 'og:type', metadata.type);
    setMetaContent('meta[property="og:url"]', 'property', 'og:url', canonicalUrl);
    setMetaContent('meta[property="og:image"]', 'property', 'og:image', imageUrl);
    setMetaContent('meta[name="twitter:card"]', 'name', 'twitter:card', 'summary_large_image');
    setMetaContent('meta[name="twitter:title"]', 'name', 'twitter:title', metadata.title);
    setMetaContent('meta[name="twitter:description"]', 'name', 'twitter:description', metadata.description);
    setMetaContent('meta[name="twitter:image"]', 'name', 'twitter:image', imageUrl);
  }, [metadata]);
}

function SiteNav({ activeSection }: { activeSection?: HomeSection }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className={`site-nav${isMenuOpen ? ' site-nav--open' : ''}`}>
      <a className="site-nav__brand" href={homeHref}>
        <span>VLAD MAFTEI</span>
        <small><b>VFX</b><b>/</b><b>3D</b><b>/</b><b>AI</b></small>
      </a>
      <button className="site-nav__toggle" type="button" aria-label="Toggle navigation" aria-controls="main-navigation" aria-expanded={isMenuOpen} onClick={() => setIsMenuOpen((current) => !current)}>
        <span />
        <span />
        <span />
      </button>
      <nav aria-label="Main navigation" id="main-navigation">
        {navLinks.map((link) => (
          <a
            className={activeSection === link.section ? 'is-active' : undefined}
            href={link.href}
            aria-current={activeSection === link.section ? 'location' : undefined}
            key={link.href}
            onClick={() => setIsMenuOpen(false)}
          >
            {link.label}
          </a>
        ))}
      </nav>
    </header>
  );
}

function useActiveHomeSection(): HomeSection | undefined {
  const [activeSection, setActiveSection] = useState<HomeSection>();

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const activationLine = Math.min(window.innerHeight * 0.34, 300);
      let current: HomeSection | undefined;

      for (const section of homeSections) {
        const element = document.getElementById(section);
        const bounds = element?.getBoundingClientRect();
        if (bounds && bounds.top <= activationLine && bounds.bottom > activationLine) current = section;
      }

      setActiveSection(current);
    };
    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
    };
  }, []);

  return activeSection;
}

function SectionHeader({
  eyebrow,
  titleId,
  title,
  children
}: {
  eyebrow: string;
  titleId: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="section-header">
      <p className="eyebrow">_{eyebrow}</p>
      <h2 id={titleId}>{title}</h2>
      {children ? <div className="section-header__copy">{children}</div> : null}
    </div>
  );
}

function useActiveHomeBunny(): ActiveBunny {
  const [activeBunny, setActiveBunny] = useState<ActiveBunny>('hero');

  useEffect(() => {
    let frame = 0;

    const updateActiveBunny = () => {
      frame = 0;
      const workSection = document.querySelector<HTMLElement>('#work');
      if (!workSection) return;

      const workBounds = workSection.getBoundingClientRect();
      const workIsFocus = workBounds.top <= window.innerHeight * 0.28
        && workBounds.bottom >= window.innerHeight * 0.2;

      setActiveBunny(workIsFocus ? 'work' : 'hero');
    };

    const scheduleUpdate = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(updateActiveBunny);
    };

    updateActiveBunny();
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);
    };
  }, []);

  return activeBunny;
}

function HomePage() {
  const heroRef = useRef<HTMLElement>(null);
  const [nowPlaying, setNowPlaying] = useState<ReelShot | null>(null);
  const activeBunny = useActiveHomeBunny();
  const activeSection = useActiveHomeSection();
  const breakdownProject = projects.find((project) => project.breakdown?.length);
  useReveal('home');

  return (
    <>
      <SiteNav activeSection={activeSection} />

      <section className="hero" ref={heroRef} aria-labelledby="hero-title">
        {/* The reel owns the first screen; only faint camera-style readouts sit on it. */}
        <div className="hero-stage">
          <HeroReel sectionRef={heroRef} onShotChange={setNowPlaying} />
          <div className="hero-hud">
            <div className="hero-hud__lines">
              <NowPlaying shot={nowPlaying} />
              <HeroTerminalLine />
            </div>
            <div className="hero-hud__meta" aria-hidden="true">
              <span>REEL / 2025—2026</span>
            </div>
          </div>
        </div>
        <div className="hero-identity">
          <div className="hero-identity__name">
            <h1 id="hero-title">
              <GlitchText text="VLAD" as="span" className="hero-name-line hero-name-line--vlad" />
              <GlitchText text="MAFTEI" as="span" className="hero-name-line" />
            </h1>
            <p className="eyebrow">3D generalist / VFX / AI video — Bucharest</p>
            <p className="hero-status"><i aria-hidden="true" /> {availability}</p>
          </div>
          <p className="hero-summary">
            I make cinematic images with 3D, simulation and generative video: creature animation and fur,
            product CGI and digital humans, LTX film sequences and point-cloud music videos.
          </p>
          {/* Buttons and social icons share one row so they always line up. */}
          <div className="hero-identity__actions">
            <a className="button button--signal" href={homeSectionHref('work')}>&gt; View work_</a>
            <a className="button" href={`mailto:${contactEmail}`}>Email me</a>
            <SocialIcons className="hero-social" />
          </div>
        </div>
      </section>

      <section id="work" className="work-section" aria-labelledby="work-title">
        {activeBunny === 'work' ? <AsciiBunny key="work-bunny" variant="work" /> : null}
        <SectionHeader eyebrow="WORK" titleId="work-title" title="Selected work">
          <p>AI video, CGI, simulation and product work. Pieces play on hover (or as you scroll on a phone); older projects live in the archive below.</p>
        </SectionHeader>
        <WorkShowcase featured={featuredProjects} archive={archiveProjects} />
      </section>

      <section id="process" className="process-section" aria-labelledby="process-title">
        <SectionHeader eyebrow="PROCESS" titleId="process-title" title="Pipeline, not prompts">
          <p>
            AI shots are steered by structure: a 3D render, a pose or a depth pass locks performance, framing
            and timing before a model touches the look. Drag through the passes from{' '}
            {breakdownProject ? <a href={projectHref(breakdownProject.slug ?? '')}>{breakdownProject.title}</a> : 'a recent shot'}.
          </p>
        </SectionHeader>
        {breakdownProject?.breakdown ? <BreakdownSlider pairs={breakdownProject.breakdown} title={breakdownProject.title} ratio={breakdownProject.breakdownRatio} /> : null}
        <ol className="process-steps">
          {processSteps.map((step, index) => (
            <li key={step.title} data-reveal>
              <span>_{String(index + 1).padStart(2, '0')}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      {articles.length > 0 ? (
        <section id="articles" className="articles-section" aria-labelledby="articles-title">
          <SectionHeader eyebrow="ARTICLES / CASE STUDIES" titleId="articles-title" title="Field Notes">
            <p>
              {featuredArticle ? <>Current featured note: <a href={featuredArticle.href}>{featuredArticle.title}</a>.</> : null}
            </p>
          </SectionHeader>
          <ArticleIndex articles={articles} />
        </section>
      ) : null}

      <section id="about" className="pages-section about-section" aria-labelledby="about-title">
        <SectionHeader eyebrow="ABOUT" titleId="about-title" title="Artist profile">
          <p>
            3D generalist from Bucharest working across VFX, product CGI, digital humans, procedural motion and
            AI-driven image and video. I like projects where image-making, lookdev, motion and technical problem
            solving meet. <a href={pageHref('about')}>Full profile -&gt;</a>
          </p>
        </SectionHeader>
        <dl className="profile-facts">
          {profileFacts.map((group) => (
            <div key={group.label} data-reveal>
              <dt>{group.label}</dt>
              {group.items.map((item) => <dd key={item}>{item}</dd>)}
            </div>
          ))}
        </dl>
      </section>

      <section id="contact" className="contact-section" aria-labelledby="contact-title">
        <SectionHeader eyebrow="CONTACT" titleId="contact-title" title="Let's make something">
          <p>Commissions, collaborations, breakdown requests or availability: email is fastest.</p>
        </SectionHeader>
        <ContactBlock />
      </section>
    </>
  );
}

export function App() {
  const route = useLocationRoute();
  useSmoothScroll();
  useHomeSectionScroll(route);
  const article = route.type === 'article' ? getArticle(route.slug) : undefined;
  const page = route.type === 'page' ? getPage(route.slug) : undefined;
  const project = route.type === 'project' ? getProject(route.slug) : undefined;
  const projectIndex = project ? projects.findIndex((candidate) => candidate.slug === project.slug) : -1;
  const previousProject = projectIndex >= 0 ? projects[(projectIndex - 1 + projects.length) % projects.length] : undefined;
  const nextProject = projectIndex >= 0 ? projects[(projectIndex + 1) % projects.length] : undefined;
  const defaultImage = 'assets/share/vladmaftei-share.jpg';
  const metadata: RouteMetadata = project
    ? {
      title: `${project.title} — Vlad Maftei`,
      description: project.description ?? `${project.title}, a portfolio project by Vlad Maftei.`,
      image: project.cover,
      canonicalPath: projectHref(project.slug ?? (route.type === 'project' ? route.slug : '')),
      type: 'article'
    }
    : article
      ? {
        title: `${article.title} — Vlad Maftei`,
        description: article.excerpt ?? `${article.title}, a field note by Vlad Maftei.`,
        image: article.cover ?? defaultImage,
        canonicalPath: articleHref(article.slug),
        type: 'article'
      }
      : page
        ? {
          title: `${page.title} — Vlad Maftei`,
          description: page.excerpt ?? `${page.title} — Vlad Maftei.`,
          image: page.cover ?? defaultImage,
          canonicalPath: pageHref(page.slug),
          type: 'website'
        }
        : {
          title: 'Vlad Maftei — VFX / 3D / AI',
          description: 'Vlad Maftei portfolio: cinematic visual work across VFX, 3D, procedural systems, product imagery, character experiments, and AI-assisted workflows.',
          image: defaultImage,
          canonicalPath: homeHref,
          type: 'website'
        };
  useRouteMetadata(metadata);

  return (
    <main className="site-shell">
      <div className="crt-overlay" aria-hidden="true" />
      {route.type === 'article' && article ? <ContentPage document={article} /> : null}
      {route.type === 'page' && page ? <ContentPage document={page} /> : null}
      {route.type === 'project' && project ? <ProjectDetailPage project={project} previousProject={previousProject} nextProject={nextProject} /> : null}
      {route.type === 'home' ? <HomePage /> : null}
      {((route.type === 'article' && !article) || (route.type === 'page' && !page) || (route.type === 'project' && !project)) ? <NotFoundPage /> : null}
    </main>
  );
}
