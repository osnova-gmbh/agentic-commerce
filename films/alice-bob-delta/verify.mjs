import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const vidder = process.env.VIDDER_ROOT || resolve(here, '../../../vidder');
const require = createRequire(resolve(vidder, 'package.json'));
const puppeteer = require('puppeteer-core');
const executablePath = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const meta = JSON.parse(await readFile(resolve(here, 'out/alice-bob-delta-render.json'), 'utf8'));
assert.equal(meta.frames, 624);
assert.equal(meta.outputFrames, 624);
assert.equal(meta.outputFps, 24);
assert.equal(meta.duration, 26);
assert.equal(meta.audio, true);
assert.equal(meta.size.w, 1920);
assert.equal(meta.size.h, 1080);
const browser = await puppeteer.launch({ executablePath, headless: true });
const errors = [], external = [];
const report = { metadata: meta, seekFrames: [], characterDrawings: 0, browserErrors: errors, externalRequests: external };
try {
  const page = await browser.newPage();
  page.on('pageerror', error => errors.push(String(error)));
  page.on('requestfailed', request => errors.push(`Request failed: ${request.url()}`));
  page.on('request', request => { if (/^https?:/.test(request.url())) external.push(request.url()); });
  const url = pathToFileURL(resolve(here, 'alice-bob-delta.html'));
  url.search = '?bare=1';
  await page.goto(url.href);
  await page.waitForFunction(() => window.__ready === true);
  const runtime = await page.evaluate(() => ({ frames: window.__NDRAW, fps: window.__fps, fonts: document.fonts.check('800 58px Manrope'), poses: Object.values(window.AD_ART.raw).map(p => ({ feet:p.feet, hand:p.hand })) }));
  assert.equal(runtime.frames, 624);
  assert.equal(runtime.fps, 24);
  assert.equal(runtime.fonts, true);
  for (const pose of runtime.poses) {
    assert.deepEqual(pose.feet, [[-50,5],[45,5]], 'Standing pose moves a planted foot');
    assert.ok(pose.hand.every(Number.isFinite), 'Invalid hand contact');
  }
  report.characterDrawings = runtime.poses.length;
  const hash = value => createHash('sha256').update(value).digest('hex');
  const chosen = [0, 95, 96, 132, 144, 250, 368, 431, 432, 500, 552, 623];
  for (const frame of chosen) {
    const before = hash(await page.evaluate(i => window.__frame(i), frame));
    await page.evaluate(() => { window.__frame(623); window.__frame(0); window.__grid(6); });
    const after = hash(await page.evaluate(i => window.__frame(i), frame));
    assert.equal(before, after, `Non-deterministic reordered seek at ${frame}`);
    report.seekFrames.push({ frame, sha256: after });
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  // Test the real encoded video, not only the source canvas or metadata sidecar.
  const viewer = await browser.newPage();
  viewer.on('pageerror', error => errors.push(String(error)));
  await viewer.goto('http://127.0.0.1:4174/');
  await viewer.waitForFunction(() => document.querySelector('video').readyState >= 1);
  const media = await viewer.evaluate(() => {
    const v = document.querySelector('video');
    return { duration:v.duration, width:v.videoWidth, height:v.videoHeight, error:v.error };
  });
  assert.equal(media.duration, 26);
  assert.equal(media.width, 1920);
  assert.equal(media.height, 1080);
  assert.equal(media.error, null);
  for (const time of [10.5, 20, 3, 25.4]) {
    await viewer.evaluate(t => { document.querySelector('video').currentTime = t; }, time);
    await viewer.waitForFunction(t => {
      const v = document.querySelector('video');
      return !v.seeking && v.readyState >= 2 && Math.abs(v.currentTime-t)<.1;
    }, {}, time);
  }
  await viewer.evaluate(async () => { const v=document.querySelector('video');v.muted=true;v.currentTime=0;await v.play(); });
  await viewer.waitForFunction(() => document.querySelector('video').ended, { timeout: 35000 });
  const playback = await viewer.evaluate(() => {
    const v = document.querySelector('video'), q = v.getVideoPlaybackQuality();
    return { ended:v.ended, currentTime:v.currentTime, totalFrames:q.totalVideoFrames, droppedFrames:q.droppedVideoFrames, error:v.error };
  });
  assert.equal(playback.ended, true);
  assert.equal(playback.error, null);
  assert.ok(playback.totalFrames >= 624);
  await viewer.screenshot({ path:resolve(here,'out/viewer-desktop.png') });
  await viewer.setViewport({ width:390,height:844,isMobile:true,deviceScaleFactor:1 });
  assert.ok(await viewer.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await viewer.screenshot({ path:resolve(here,'out/viewer-mobile.png') });
  const range = await fetch('http://127.0.0.1:4174/video.mp4', { headers:{ Range:'bytes=0-99' } });
  assert.equal(range.status, 206);
  assert.equal((await range.arrayBuffer()).byteLength, 100);
  const invalid = await fetch('http://127.0.0.1:4174/video.mp4', { headers:{ Range:'bytes=999999999999-' } });
  assert.equal(invalid.status, 416);
  assert.equal((await fetch('http://127.0.0.1:4174/FILM.md')).status, 404);
  assert.deepEqual(errors, []);
  report.encodedVideo = media;
  report.playback = playback;
  report.rangeRequests = 'passed';
  report.mobileOverflow = false;
  report.limitations = 'Contact sheets, stills and consecutive frames reviewed visually. Encoded playback tested automatically at 1x; no real-time visual or listening review.';
  await writeFile(resolve(here,'out/verification.json'), JSON.stringify(report,null,2)+'\n');
  console.log(`PASS: ${report.characterDrawings} whole drawings, ${chosen.length} repeat-after-seek comparisons, 624-frame 1080p video, full 26-second browser playback, mobile layout and byte-range delivery.`);
} finally { await browser.close(); }
