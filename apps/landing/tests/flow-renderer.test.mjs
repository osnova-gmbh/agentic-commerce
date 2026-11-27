import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const data = await readFile(new URL('../../../films/commerce-flow/flow-data.js', import.meta.url), 'utf8');
const film = await readFile(new URL('../../../films/commerce-flow/film.js', import.meta.url), 'utf8');

function context() {
  const calls = [];
  const drawing = new Proxy({
    measureText(text) { return { width: text.length * 12 }; },
  }, {
    get(target, name) {
      return target[name] || ((...args) => calls.push([name, ...args]));
    },
    set(target, name, value) { target[name] = value; calls.push([name, value]); return true; },
  });
  return { drawing, calls };
}

test('landing renderer loads without Vidder and draws every chapter', () => {
  const sandbox = vm.createContext({ window: {} });
  vm.runInContext(data, sandbox);
  vm.runInContext(film, sandbox);
  const renderer = sandbox.window.CommerceFlowRenderer;
  assert.equal(renderer.duration, 62);
  assert.equal(renderer.width, 1920);
  assert.equal(renderer.height, 1080);
  const { drawing, calls } = context();
  for (const chapter of sandbox.window.COMMERCE_FLOW.phases) {
    renderer.renderFrame(drawing, (chapter.offset + 1.5) * 24);
    assert.ok(calls.some((call) => call[0] === 'fillText' && call[1] === chapter.title));
  }
});

test('landing frames match the unchanged Vidder timeline drawing', async () => {
  let exportConfig;
  const sandbox = vm.createContext({
    window: {}, document: { fonts: { load: async () => [] } },
    defineFilm(config) { exportConfig = config; },
    PALETTES: { pencilMinimal: {} },
  });
  vm.runInContext(data, sandbox);
  vm.runInContext(film, sandbox);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(exportConfig.timeline.length, 8);
  assert.equal(exportConfig.fps, 24);
  assert.equal(exportConfig.format.width, 1920);
  for (const [index, chapter] of sandbox.window.COMMERCE_FLOW.phases.entries()) {
    const frame = (chapter.offset + 1.5) * 24;
    const embedded = context();
    const exported = context();
    sandbox.window.CommerceFlowRenderer.renderFrame(embedded.drawing, frame);
    exportConfig.timeline[index].fn(exported.drawing, 1.5);
    assert.deepEqual(embedded.calls, exported.calls);
  }
});
