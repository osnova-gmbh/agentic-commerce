// @ts-check
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const port = Number(process.env.PORT || 4173);
/** @type {Record<string, [string, string]>} */
const routes = {
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/index.html': ['index.html', 'text/html; charset=utf-8'],
  '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
  '/hero.css': ['hero.css', 'text/css; charset=utf-8'],
  '/workspace.css': ['workspace.css', 'text/css; charset=utf-8'],
  '/responsive.css': ['responsive.css', 'text/css; charset=utf-8'],
  '/demo.js': ['demo.js', 'text/javascript; charset=utf-8'],
  '/assets/mark.svg': ['assets/mark.svg', 'image/svg+xml'],
  '/assets/manrope-latin.woff2': ['assets/manrope-latin.woff2', 'font/woff2'],
  '/SPEC.md': ['../../SPEC.md', 'text/plain; charset=utf-8'],
};

const server = createServer(async (request, response) => {
  try {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405, { Allow: 'GET, HEAD' }).end('Method not allowed');
      return;
    }
    const pathname = new URL(request.url || '/', 'http://localhost').pathname;
    const route = Object.hasOwn(routes, pathname) ? routes[pathname] : undefined;
    if (!route) {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found');
      return;
    }
    const [path, type] = route;
    const content = await readFile(new URL(path, import.meta.url));
    response.writeHead(200, {
      'Content-Type': type,
      'Content-Length': content.byteLength,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    });
    response.end(request.method === 'HEAD' ? undefined : content);
  } catch (error) {
    console.error('Landing preview request failed:', error instanceof Error ? error.message : 'Unknown error');
    if (!response.headersSent) response.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Unable to load the preview. Check the local server output.');
  }
});

server.on('error', (error) => {
  console.error(`Could not start the preview on 127.0.0.1:${port}: ${error.message}`);
  process.exitCode = 1;
});
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error('PORT must be an integer between 1 and 65535.');
  process.exitCode = 1;
} else {
  server.listen(port, '127.0.0.1', () => console.log(`Cogit Finance concept: http://127.0.0.1:${port}`));
}
