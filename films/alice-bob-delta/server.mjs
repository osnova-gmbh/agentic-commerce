import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('./', import.meta.url);
const routes = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/video.mp4', ['out/alice-bob-delta-final.mp4', 'video/mp4']],
  ['/poster.png', ['out/alice-bob-delta-frames/0610.png', 'image/png']],
  ['/contact.jpg', ['out/alice-bob-delta-contact.jpg', 'image/jpeg']],
  ['/alice-bob-delta.html', ['alice-bob-delta.html', 'text/html; charset=utf-8']],
  ...['drawings.js', 'film.js', 'engine/core.js', 'engine/studio.js', 'engine/cels.js'].map(path => [`/${path}`, [path, 'text/javascript; charset=utf-8']]),
  ['/assets/font.css', ['assets/font.css', 'text/css; charset=utf-8']],
]);
const server = createServer(async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }); res.end(); return; }
  const route = routes.get((req.url || '/').split('?')[0]);
  if (!route) { res.writeHead(404); res.end(); return; }
  const [relative, type] = route;
  const file = fileURLToPath(new URL(relative, root));
  try {
    const { size } = await stat(file);
    res.setHeader('Content-Type', type);
    res.setHeader('Accept-Ranges', 'bytes');
    let start = 0, end = size - 1, status = 200;
    if (req.headers.range) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
      if (match && (match[1] || match[2])) {
        if (match[1]) { start = Number(match[1]); end = match[2] ? Math.min(Number(match[2]), end) : end; }
        else { start = Math.max(0, size - Number(match[2])); }
      }
      if (!match || !(match[1] || match[2]) || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start > end || start >= size) {
        res.writeHead(416, { 'Content-Range': `bytes */${size}` }); res.end(); return;
      }
      status = 206;
      res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`);
    }
    res.setHeader('Content-Length', end - start + 1);
    res.writeHead(status);
    if (req.method === 'HEAD') { res.end(); return; }
    const stream = createReadStream(file, { start, end });
    stream.on('error', () => res.destroy());
    res.on('close', () => stream.destroy());
    stream.pipe(res);
  } catch { if (!res.headersSent) res.writeHead(404); res.end(); }
});
server.listen(4174, '127.0.0.1', () => console.log('Film: http://127.0.0.1:4174/'));
