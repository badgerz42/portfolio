import { expect, test } from '@playwright/test';

test('home exposes finished work without the draft article', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1 })).toContainText('VLAD');
  await expect(page.getByRole('heading', { name: 'Night of the Living Dead - LTX-2 Contest', exact: true })).toBeVisible();
  await expect(page.getByText('Building a Cyberpunk Bucharest with AI')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Articles', exact: true })).toHaveCount(0);
});

test('work section leads with a featured grid, an archive list, and discipline filters', async ({ page }) => {
  await page.goto('/#work');

  const tiles = page.locator('.work-bento .work-tile');
  const rows = page.locator('.archive__list li');
  await expect(tiles).toHaveCount(8);
  await expect(rows).toHaveCount(8);
  // Newest first, and the lead shape always goes to the first tile.
  await expect(tiles.locator('h3')).toHaveText([
    'Polar Bear Walk',
    'Dark Forest',
    'F1R - Fugi Live',
    'Night of the Living Dead - LTX-2 Contest',
    'F1R - Fugi Visualizer',
    'Cat Walkman',
    'Daft Punk cover art',
    'Trips'
  ]);
  await expect(tiles.nth(0)).toHaveClass(/work-tile--lead/);

  await page.getByRole('button', { name: '--product', exact: true }).click();
  await expect(page.getByRole('button', { name: '--product', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.work-tile.is-dimmed')).toHaveCount(8);
  await expect(page.locator('.archive__list li:not([hidden])')).toHaveCount(2);

  await page.getByRole('button', { name: '--all', exact: true }).click();
  await expect(page.locator('.work-tile.is-dimmed')).toHaveCount(0);
  await expect(page.locator('.archive__list li:not([hidden])')).toHaveCount(8);
});

test('home navigation marks the section currently crossing the viewport', async ({ page }) => {
  await page.goto('/');

  await page.locator('#process').scrollIntoViewIfNeeded();
  await expect(page.locator('#main-navigation a[href="/#process"]')).toHaveClass(/is-active/);

  await page.locator('#contact').scrollIntoViewIfNeeded();
  await expect(page.locator('#main-navigation a[href="/#contact"]')).toHaveClass(/is-active/);
});

test('clean project routes have specific metadata and return to the work archive', async ({ page }) => {
  await page.goto('/projects/cat-walkman/');

  await expect(page).toHaveTitle('Cat Walkman — Vlad Maftei');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'http://127.0.0.1:4174/projects/cat-walkman/');

  await page.getByRole('link', { name: 'WORK', exact: true }).click();
  await expect(page).toHaveURL(/\/#work$/);
  await expect.poll(async () => page.locator('#work').evaluate((element) => Math.abs(element.getBoundingClientRect().top))).toBeLessThan(100);
});

test('mobile hero remains readable, contained, and compact', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Mobile-specific layout check');
  await page.goto('/');

  const menu = page.getByRole('button', { name: 'Toggle navigation' });
  await expect(menu).toBeVisible();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('link', { name: 'Contact', exact: true })).toBeVisible();

  const metrics = await page.evaluate(() => {
    const title = document.querySelector('.hero h1')?.getBoundingClientRect();
    const summary = document.querySelector('.hero-summary');
    const terminal = document.querySelector('.hero-terminal-line');
    return {
      width: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      summaryFont: summary ? Number.parseFloat(getComputedStyle(summary).fontSize) : 0,
      titleInside: Boolean(title && title.left >= 0 && title.right <= document.documentElement.clientWidth + 1),
      terminalFits: Boolean(terminal && terminal.scrollWidth <= terminal.clientWidth + 1)
    };
  });

  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.width);
  expect(metrics.summaryFont).toBeGreaterThanOrEqual(14);
  expect(metrics.titleInside).toBe(true);
  expect(metrics.terminalFits).toBe(true);
});

test('hero shows the reel with a primary call to action', async ({ page }) => {
  await page.goto('/');

  await expect(page.locator('.hero-reel')).toHaveCount(1);
  await expect(page.locator('.hero-reel__video')).toHaveCount(1);
  const cta = page.locator('.hero-identity__actions .button--signal');
  await expect(cta).toHaveAttribute('href', '/#work');
  await expect(cta).toHaveCSS('background-color', 'rgb(166, 255, 0)');

  // The reel HUD names the project on screen and links to it.
  const nowPlaying = page.locator('.now-playing');
  await expect(nowPlaying).toHaveAttribute('href', /^\/projects\/[a-z0-9-]+\/$/);
  await expect(nowPlaying).toContainText('now_playing:');
  await expect(page.locator('.decrypt')).toHaveCount(0);

  const socials = page.locator('.hero-social a');
  await expect(socials).toHaveCount(4);
  for (const name of ['ArtStation', 'LinkedIn', 'Instagram', 'X']) {
    await expect(page.locator('.hero-social').getByRole('link', { name: new RegExp(`^${name}:`) })).toHaveAttribute('target', '_blank');
  }
});

test('local video collections defer playback until selected', async ({ page }) => {
  await page.goto('/projects/x-particles-challenge-2018/');

  await expect(page.locator('.project-video__poster')).toHaveCount(10);
  await expect(page.locator('.project-video video')).toHaveCount(0);

  await page.getByRole('button', { name: 'Play X-Particles animation test 01' }).click();
  await expect(page.locator('.project-video video')).toHaveCount(1);
});

test('the merged X-Particles project keeps its old URL working', async ({ page }) => {
  await page.goto('/projects/xparticles-challenge-2018-animation-tests-and-explorations/');

  await expect(page.getByRole('heading', { level: 1 })).toContainText('X-Particles Challenge 2018');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'http://127.0.0.1:4174/projects/x-particles-challenge-2018/');
});

test('project meta line has no duplicate tags and private videos are not embedded', async ({ page }) => {
  await page.goto('/projects/philips-sensotouch/');

  const meta = (await page.locator('.content-hero__meta').innerText()).split('/').map((item) => item.trim().toLowerCase());
  expect(new Set(meta).size).toBe(meta.length);
  await expect(page.locator('iframe[src*="QoMyGzBPKAo"]')).toHaveCount(0);
});

test('LTX contest dossier leads with the final and defers inline WIP playback', async ({ page }) => {
  await page.goto('/projects/night-of-the-living-dead-ltx-contest/');

  await expect(page).toHaveTitle('Night of the Living Dead - LTX-2 Contest — Vlad Maftei');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Night of the Living Dead');
  await expect(page.getByRole('button', { name: 'Play Final contest sequence' })).toBeVisible();
  await expect(page.locator('.ascii-bunny--zombie')).toHaveCount(1);
  await expect(page.locator('.content-video__poster')).toHaveCount(3);
  await expect(page.locator('.content-video video')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'The Constraint' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'ComfyUI Graph' })).toBeVisible();

  await page.getByRole('button', { name: 'Play LTX-2 pose-guided motion test' }).click();
  await expect(page.locator('.content-video video')).toHaveCount(1);

  const breakdown = page.locator('.breakdown').first();
  await expect(breakdown.locator('.breakdown__stages button')).toHaveCount(3);
  await breakdown.locator('.breakdown__range').fill('20');
  await expect(breakdown.locator('.breakdown__frame')).toHaveAttribute('style', /--wipe: 20%/);
});

test('project dossiers expose sticky contents and deliberate previous-next exits', async ({ page }, testInfo) => {
  await page.goto('/projects/fugi-visualizer/');

  const utilityRail = page.locator('.project-utility-rail');
  await expect(utilityRail).toHaveCSS('position', 'sticky');
  await expect(page.locator('#project-signal')).toHaveCount(1);
  await expect(page.locator('#what-i-made-with-codex')).toHaveCount(1);
  await expect(page.locator('#f1r-character-explorations')).toHaveCount(1);
  await expect(page.locator('#extended-video-tests')).toHaveCount(1);

  if (testInfo.project.name === 'mobile') {
    const menu = page.locator('.project-contents--mobile');
    await expect(menu).toBeVisible();
    await menu.locator('summary').click();
    await expect(menu.getByRole('link', { name: '03 CHARACTER', exact: true })).toBeVisible();
  } else {
    const contents = page.locator('.project-contents--desktop');
    await expect(contents).toBeVisible();
    await expect(contents.getByRole('link')).toHaveCount(4);
  }

  await expect(page.locator('.project-exit-nav__previous')).toHaveAttribute('href', '/projects/polar-bear-walk/');
  await expect(page.locator('.project-exit-nav__archive')).toHaveAttribute('href', '/#work');
  await expect(page.locator('.project-exit-nav__next')).toHaveAttribute('href', '/projects/night-of-the-living-dead-ltx-contest/');
});

test('project images remain contained within the viewport height', async ({ page }) => {
  await page.goto('/projects/fugi-visualizer/');

  const image = page.locator('.content-image img').first();
  await image.scrollIntoViewIfNeeded();
  const dimensions = await image.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return { height: bounds.height, viewportHeight: window.innerHeight, objectFit: getComputedStyle(element).objectFit };
  });

  expect(dimensions.height).toBeLessThanOrEqual(dimensions.viewportHeight * 0.82 + 1);
  expect(dimensions.objectFit).toBe('contain');
});

test('full-resolution viewer supports fit, actual pixels, navigation, and focus return', async ({ page }) => {
  await page.goto('/projects/trips/');

  const trigger = page.getByRole('button', { name: 'Inspect Trips artwork 1 full resolution' });
  await trigger.click();

  const viewer = page.getByRole('dialog', { name: 'Full-resolution image viewer' });
  const image = viewer.locator('.image-viewer__viewport img');
  await expect(viewer).toBeVisible();
  await expect(page).toHaveURL(/\/projects\/trips\/$/);
  await expect(viewer.getByRole('button', { name: 'FIT', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(image).toHaveAttribute('src', /\/assets\/artstation\/trips\//);

  await viewer.getByRole('button', { name: '100%', exact: true }).click();
  await expect(viewer.getByRole('button', { name: '100%', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(viewer.locator('.image-viewer__viewport')).toHaveClass(/image-viewer__viewport--actual/);
  await expect(image).toHaveCSS('max-width', 'none');

  const firstSource = await image.getAttribute('src');
  await viewer.getByRole('button', { name: 'Next image' }).click();
  await expect(viewer.getByText(/02 \/ \d{2}/)).toBeVisible();
  await expect.poll(() => image.getAttribute('src')).not.toBe(firstSource);

  await page.keyboard.press('ArrowLeft');
  await expect(viewer.getByText(/01 \/ \d{2}/)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect(page.locator('body')).not.toHaveClass(/image-viewer-open/);
});

test('article images open in the same full-resolution viewer', async ({ page }) => {
  await page.goto('/projects/fugi-visualizer/');

  const trigger = page.locator('.content-image__full-link').first();
  await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
  await trigger.click();
  await expect(page.getByRole('dialog', { name: 'Full-resolution image viewer' })).toBeVisible();
  await expect(page.locator('.image-viewer__viewport img')).toHaveAttribute('src', /\/assets\/projects\/fugi-visualizer\/.*\.png$/);
});

test('FIT contains every F1R image at ultrawide resolution', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Ultrawide-specific layout check');
  await page.setViewportSize({ width: 2560, height: 1080 });
  await page.goto('/projects/fugi-visualizer/');

  const imageCount = await page.locator('.content-image__full-link').count();
  const viewerImage = page.locator('.image-viewer__viewport img');
  await page.locator('.content-image__full-link').first().click();

  for (let index = 0; index < imageCount; index += 1) {
    await expect.poll(() => viewerImage.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    const bounds = await viewerImage.evaluate((element) => {
      const image = element.getBoundingClientRect();
      const viewport = element.closest('.image-viewer__viewport')!.getBoundingClientRect();
      return {
        image: { left: image.left, top: image.top, right: image.right, bottom: image.bottom },
        viewport: { left: viewport.left, top: viewport.top, right: viewport.right, bottom: viewport.bottom }
      };
    });

    expect(bounds.image.left).toBeGreaterThanOrEqual(bounds.viewport.left - 1);
    expect(bounds.image.top).toBeGreaterThanOrEqual(bounds.viewport.top - 1);
    expect(bounds.image.right).toBeLessThanOrEqual(bounds.viewport.right + 1);
    expect(bounds.image.bottom).toBeLessThanOrEqual(bounds.viewport.bottom + 1);

    if (index < imageCount - 1) {
      const currentSource = await viewerImage.getAttribute('src');
      await page.getByRole('button', { name: 'Next image' }).click();
      await expect.poll(() => viewerImage.getAttribute('src')).not.toBe(currentSource);
    }
  }
});

test('featured tiles reveal full colour, copy, and motion on hover', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Hover feedback is desktop-specific');
  await page.goto('/#work');

  const tile = page.locator('.work-tile').first();
  await tile.scrollIntoViewIfNeeded();
  await tile.hover();
  await expect(tile.locator('.work-tile__media img')).toHaveCSS('filter', 'none');
  await expect(tile.locator('.work-tile__info p')).toHaveCSS('opacity', '1');
  await expect(tile.locator('video.work-loop')).toHaveAttribute('src', /\/assets\/generated\/loops\/polar-bear-walk\.mp4$/);
});

test('videos precede gallery images and the text toggle reports its state', async ({ page }) => {
  await page.goto('/projects/cat-walkman/');

  const order = await page.evaluate(() => ({
    videoTop: document.querySelector('.project-videos')?.getBoundingClientRect().top ?? 0,
    galleryTop: document.querySelector('.project-gallery')?.getBoundingClientRect().top ?? 0
  }));
  expect(order.videoTop).toBeLessThan(order.galleryTop);

  const toggle = page.locator('.project-view-tools button');
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.content-hero__excerpt')).toBeHidden();
});

test('F1R live video case study leads with the film and documents the pipeline', async ({ page }) => {
  await page.goto('/projects/f1r-live-video/');

  await expect(page).toHaveTitle('F1R - Fugi Live — Vlad Maftei');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('F1R - Fugi Live');
  await expect(page.getByRole('button', { name: 'Play F1R - Fugi (live point performance), full music video' })).toBeVisible();
  for (const heading of ['The Brief', 'Singing Performance With LTX-2.3', 'From Video To Points', 'A Camera That Listens']) {
    await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  }
  await expect(page.locator('.content-video__poster')).toHaveCount(1);
  await expect(page.locator('.project-exit-nav__previous')).toHaveAttribute('href', '/projects/night-of-the-living-dead-ltx-contest/');
});

test('Dark Forest page has draggable turntables and an inline pass breakdown', async ({ page }) => {
  await page.goto('/projects/dark-forest/');

  await expect(page).toHaveTitle('Dark Forest — Vlad Maftei');
  await expect(page.getByRole('button', { name: 'Play Dark Forest, final shot (28 seconds, with sound)' })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/castlevania|staticvfx/i);

  const turntable = page.locator('.turntable');
  await expect(turntable.locator('.turntable__assets button')).toHaveCount(7);
  const stage = turntable.locator('.turntable__stage');
  await stage.scrollIntoViewIfNeeded();
  await stage.focus();
  await page.keyboard.press('ArrowRight');
  const before = Number(await stage.getAttribute('aria-valuenow'));
  await page.keyboard.press('ArrowRight');
  await expect(stage).toHaveAttribute('aria-valuenow', String((before + 10) % 360));
  await turntable.getByRole('button', { name: /Lantern/ }).click();
  await expect(stage.locator('img')).toHaveAttribute('src', /turntables\/lantern\/00\.webp$/);

  // Every asset's rendered (object-fit: contain) frame must sit inside the stage, never cropped.
  for (const name of ['Traveller', 'Backpack', 'Stump + trunk', 'Forest spirit']) {
    await turntable.getByRole('button', { name: new RegExp(name.replace('+', '\\+')) }).click();
    const fits = await stage.evaluate(async (element) => {
      const image = element.querySelector('img') as HTMLImageElement;
      await image.decode().catch(() => undefined);
      const box = element.getBoundingClientRect();
      const rect = image.getBoundingClientRect();
      const scale = Math.min(rect.width / image.naturalWidth, rect.height / image.naturalHeight);
      const width = image.naturalWidth * scale;
      const height = image.naturalHeight * scale;
      const left = rect.left + (rect.width - width) / 2;
      const top = rect.top + (rect.height - height) / 2;
      return left >= box.left - 1 && top >= box.top - 1 && left + width <= box.right + 1 && top + height <= box.bottom + 1;
    });
    expect(fits, name).toBe(true);
  }

  const breakdown = page.locator('.content-renderer .breakdown');
  await expect(breakdown).toHaveCount(1);
  await expect(breakdown.locator('.breakdown__stages button')).toHaveCount(5);
});

test('the polar bear page shows its final shot, inline media and the CG-to-footage slider', async ({ page, request }) => {
  await page.goto('/projects/polar-bear-walk/');
  await expect(page.locator('h1')).toContainText('Polar Bear Walk');

  const breakdown = page.locator('.content-renderer .breakdown');
  await breakdown.scrollIntoViewIfNeeded();
  await expect(breakdown).toBeVisible();
  await expect(breakdown.locator('.breakdown__stages button')).toHaveCount(3);
  await expect(page.locator('.content-renderer .content-video')).toHaveCount(10);

  const sources = await page.locator('.content-renderer img').evaluateAll((images) => images.map((image) => image.getAttribute('src') ?? ''));
  expect(sources.length).toBeGreaterThan(15);
  for (const source of sources) expect((await request.get(source)).ok(), source).toBe(true);
});

test('the hero reel only features recent work (2025-2026 plus Trips)', async ({ request }) => {
  for (const file of ['reel.json', 'reel-collage.json', 'reel-doodle.json']) {
    const manifest = await (await request.get(`/assets/generated/reel/${file}`)).json();
  const recent = ['polar-bear-walk', 'f1r-live-video', 'dark-forest', 'night-of-the-living-dead-ltx-contest', 'fugi-visualizer', 'cat-walkman', 'daft-punk-cover-art', 'trips'];
    for (const shot of manifest.shots) expect(recent, shot.slug).toContain(shot.slug);
  }
});

test('the hero plays the doodle montage by default, with collage and classic on request', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.hero-reel__video')).toHaveAttribute('src', /reel-doodle-(720|480)\.mp4$/);
  await expect(page.locator('.hero-hud__meta')).toContainText('REEL / 2025—2026');
  await page.goto('/?reel=collage');
  await expect(page.locator('.hero-reel__video')).toHaveAttribute('src', /reel-collage-(720|480)\.mp4$/);
  await page.goto('/?reel=classic');
  await expect(page.locator('.hero-reel__video')).toHaveAttribute('src', /\/reel-(720|480)\.mp4$/);
});

test('the Selected work heading matches the small nav name mark', async ({ page }) => {
  await page.goto('/');
  const [brand, heading] = await page.evaluate(() => [
    getComputedStyle(document.querySelector('.site-nav__brand span')!).fontSize,
    getComputedStyle(document.querySelector('#work-title')!).fontSize
  ]);
  expect(heading).toBe(brand);
});

test('switching work filters never hides tiles that match', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Filter interaction checked once');
  await page.goto('/#work');
  // Scroll through the grid so every tile has been revealed once.
  for (const tile of await page.locator('.work-tile').all()) await tile.scrollIntoViewIfNeeded();
  await page.locator('.work-filters').scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  for (const filter of ['--ai', '--3d', '--product', '--vfx', '--all', '--ai', '--all']) {
    await page.getByRole('button', { name: filter, exact: true }).click();
    await page.waitForTimeout(300);
    const hidden = await page.locator('.work-tile:not(.is-dimmed)').evaluateAll((tiles) =>
      tiles.filter((tile) => getComputedStyle(tile).clipPath.includes('100%')).length);
    expect(hidden, `visible tiles clipped away after ${filter}`).toBe(0);
  }
  await expect(page.locator('.work-tile.is-dimmed')).toHaveCount(0);
});
