import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/dashboard/static/demo.js', import.meta.url), 'utf8');
const archivedId = '9892d6ef-fa06-44bc-9517-93bdf90fcd73';
const activeId = 'current-training';
const service = {
  seller_org_id: 'seller-co', offer_id: 'ai-training', title: 'AI training course',
  seller_name: 'Example Seller', description: 'Training for teams.', category: 'training',
  price: 'EUR 1,200.00', payout: 'EUR 1,188.00', fee: 'EUR 12.00',
  input_schema: {properties: {topic: {type: 'string'}}, required: ['topic']},
  deliverable: {required_files: ['course.md']},
};
const archived = {deal: {
  deal_id: archivedId, offer_id: 'offer-1', offer_title: 'Market report',
  buyer_org_id: 'buyer-co', seller_org_id: 'seller-co', state: 'SETTLED',
  tone: 'done', price: 'EUR 500.00',
}};
const publishedOffers = [{
  company_id: 'elephant', company_name: 'Elephant Technologies', offer_id: 'learning-platform',
  title: 'Learning and knowledge platform', description: 'Company training and knowledge tools.',
  category: 'Training', source_url: 'https://example.invalid/elephant',
  price_minor: null, currency: null, price_label: 'Request quote', pricing_basis: null,
  contact_url: 'https://example.invalid/elephant/contact',
}, {
  company_id: 'base', company_name: 'Base', offer_id: 'operations',
  title: 'Commerce operations platform', description: 'Manage commerce orders.',
  category: 'Commerce', source_url: 'https://example.invalid/base',
  price_minor: 4900, currency: 'EUR', price_label: '€49 / month',
  pricing_basis: 'Monthly subscription, billed annually', contact_url: null,
}];

class Element {
  constructor(tag, className = '', ...children) {
    this.tag = tag; this.className = className; this.children = []; this.listeners = {};
    this.disabled = false; this.append(...children);
  }
  append(...children) { this.children.push(...children.filter(value => value != null && value !== '')); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  scrollIntoView() {}
  get options() { return this.children; }
  get textContent() { return this.children.map(value => value instanceof Element ? value.textContent : String(value)).join(' '); }
  set textContent(value) { this.children = [value]; }
  querySelectorAll(selector) {
    const tags = selector.split(',').map(value => value.trim());
    return this.children.flatMap(value => value instanceof Element ? [
      ...(tags.includes(value.tag) ? [value] : []), ...value.querySelectorAll(selector),
    ] : []);
  }
}

async function harness({hash = archivedId, search = '?legacy=1', running = false, state = 'SETTLED', archiveResponse, offers = publishedOffers} = {}) {
  const elements = Object.fromEntries(['checkout-content', 'status', 'demo-controls', 'browse-services-nav']
    .map(id => [id, new Element('div')]));
  const listeners = [];
  let currentHash = hash ? '#' + hash : '';
  const requests = [];
  const current = {
    deal_id: activeId, running, state, error: null,
    order: {service, inputs: {topic: 'AI for finance teams'}, scenario: 'happy'},
    payment: service, allowed_actions: state === 'FUNDED' ? ['deliver'] : ['browse'],
  };
  const location = {
    pathname: '/demo', origin: 'http://local', search,
    get hash() { return currentHash; },
    set hash(value) {
      currentHash = value ? '#' + value.replace(/^#/, '') : '';
      queueMicrotask(() => listeners.forEach(listener => listener()));
    },
  };
  const context = vm.createContext({
    document: {getElementById: id => elements[id]},
    window: {addEventListener: (name, callback) => { if (name === 'hashchange') listeners.push(callback); }},
    location,
    URL, URLSearchParams,
    isLegacyCheckout: () => new URLSearchParams(location.search).get('legacy') === '1',
    history: {replaceState: (_state, _title, url) => {
      const next = new URL(url, 'http://local'); currentHash = next.hash; location.search = next.search;
    }},
    pinned: () => decodeURIComponent(currentHash.slice(1)),
    setTimeout: () => 0,
    crypto: {randomUUID: () => 'test-key'},
    el: (tag, cls, ...children) => new Element(tag, cls, ...children),
    pill: (_tone, _icon, text) => new Element('span', '', text),
    moneyText: text => (text || '-').replace('EUR ', '€'),
    refresh: async () => {},
    fetch: async (url, options = {}) => {
      requests.push({url, method: options.method || 'GET'});
      if (url === '/api/provider-offers') return {ok: true, json: async () => ({offers})};
      if (url === '/api/demo/services') return {ok: true, json: async () => ({services: [service]})};
      if (url === '/api/demo/status') return {ok: true, json: async () => structuredClone(current)};
      if (url === '/api/deals/' + archivedId) {
        if (archiveResponse) return archiveResponse();
        return {ok: true, json: async () => structuredClone(archived)};
      }
      return {ok: false, status: 404, json: async () => ({message: 'Unknown deal'})};
    },
  });
  vm.runInContext(source, context);
  const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await new Promise(resolve => setImmediate(resolve)); };
  await flush();
  return {
    context, current, location, requests, flush,
    text: () => elements['checkout-content'].textContent,
    status: () => elements.status.textContent,
    buttons: () => elements['checkout-content'].querySelectorAll('button'),
    links: () => elements['checkout-content'].querySelectorAll('a'),
    click: async label => {
      const button = elements['checkout-content'].querySelectorAll('button').find(node => node.textContent.startsWith(label));
      assert.ok(button, 'Missing button: ' + label);
      assert.equal(button.disabled, false, label + ' must be usable');
      button.listeners.click();
      await flush();
    },
  };
}

test('a linked archived report never shows the latest training checkout', async () => {
  const page = await harness();
  assert.match(page.text(), /Market report/);
  assert.match(page.text(), /€500\.00/);
  assert.match(page.text(), /READ-ONLY TRANSACTION/);
  assert.doesNotMatch(page.text(), /AI training course|1,200|1,188/);
  assert.ok(page.buttons().every(button => !/Fund escrow|Release payment|Simulate/.test(button.textContent)));
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Browse services')));
  assert.ok(page.requests.some(request => request.url === '/api/deals/' + archivedId));
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('the primary overview lists actual provider offers, not generic simulation products', async () => {
  const page = await harness({hash: '', search: ''});
  assert.match(page.text(), /Learning and knowledge platform/);
  assert.match(page.text(), /Commerce operations platform/);
  assert.match(page.text(), /Monthly subscription, billed annually/);
  assert.doesNotMatch(page.text(), /AI training course|Market report|1,200/);
  assert.ok(page.requests.some(request => request.url === '/api/provider-offers'));
  assert.ok(page.requests.every(request => !request.url.startsWith('/api/demo/')));
  assert.equal(page.links().find(link => link.textContent === 'View offering').href,
    '/demo?company=elephant&offer=learning-platform');
});

test('a provider deep link shows source and billing basis without escrow payment actions', async () => {
  const page = await harness({hash: '', search: '?company=base&offer=operations'});
  assert.match(page.text(), /Commerce operations platform/);
  assert.match(page.text(), /€49 \/ month/);
  assert.match(page.text(), /Monthly subscription, billed annually/);
  assert.match(page.text(), /not an agreed escrow amount/);
  assert.doesNotMatch(page.text(), /Learning and knowledge platform|AI training course/);
  assert.equal(page.links().find(link => link.textContent === 'Official details').href, 'https://example.invalid/base');
  assert.ok(page.buttons().every(button => !/Fund escrow|Release payment|Simulate/.test(button.textContent)));
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('quote and waitlist actions link only to the supplied official contact', async () => {
  const page = await harness({hash: '', search: '?company=elephant&offer=learning-platform'});
  assert.equal(page.links().find(link => link.textContent === 'Request quote').href, 'https://example.invalid/elephant/contact');
  const waitlist = await harness({hash: '', search: '?company=elephant&offer=learning-platform',
    offers: [{...publishedOffers[0], availability: 'waitlist'}]});
  assert.match(waitlist.text(), /Availability: waitlist/);
  assert.equal(waitlist.links().find(link => link.textContent === 'Join waitlist').href, 'https://example.invalid/elephant/contact');
});

test('default historical links never fetch or display the unrelated live checkout', async () => {
  const page = await harness({hash: archivedId, search: ''});
  assert.match(page.text(), /Market report/);
  assert.match(page.text(), /€500\.00/);
  assert.match(page.status(), /Read-only demo history/);
  assert.doesNotMatch(page.text(), /AI training course|1,200|1,188/);
  assert.deepEqual(page.requests.map(request => request.url), ['/api/deals/' + archivedId]);
  await page.click('Browse services');
  assert.equal(page.location.hash, '');
  assert.match(page.text(), /Learning and knowledge platform/);
});

test('an unknown provider offering does not fall back to a generic purchasable service', async () => {
  const page = await harness({hash: '', search: '?company=missing&offer=unknown'});
  assert.match(page.text(), /Offering unavailable/);
  assert.doesNotMatch(page.text(), /AI training course|Market report|Fund escrow/);
});

test('changing the hash updates the checkout context as well as the selected deal', async () => {
  const page = await harness({hash: activeId});
  assert.match(page.text(), /AI training course/);
  page.location.hash = archivedId;
  await page.flush();
  assert.match(page.text(), /Market report/);
  assert.doesNotMatch(page.text(), /1,200|1,188/);
  page.location.hash = activeId;
  await page.flush();
  assert.match(page.text(), /AI training course/);
  assert.doesNotMatch(page.text(), /READ-ONLY TRANSACTION/);
});

test('browsing from history preserves an active order and provides a way back', async () => {
  const page = await harness({running: true, state: 'FUNDED'});
  await page.click('Browse services');
  assert.equal(page.location.hash, '');
  assert.match(page.text(), /Choose the work you need/);
  const select = page.buttons().find(button => button.textContent.startsWith('Select service'));
  assert.equal(select.disabled, true, 'Cannot start another order while the live order is running');
  await page.click('View current checkout');
  assert.equal(page.location.hash, '#' + activeId);
  assert.match(page.text(), /AI training course/);
  assert.equal(page.current.deal_id, activeId);
  assert.equal(page.current.state, 'FUNDED');
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('a missing selected deal does not fall back to unrelated checkout details', async () => {
  const page = await harness({hash: 'missing-deal'});
  assert.match(page.text(), /Deal unavailable/);
  assert.match(page.status(), /Cannot load selected deal/);
  assert.doesNotMatch(page.text(), /AI training course|1,200/);
});

test('a late historical response cannot replace a newer hash selection', async () => {
  let release;
  const promise = new Promise(resolve => { release = resolve; });
  const page = await harness({archiveResponse: () => promise});
  page.location.hash = activeId;
  await page.flush();
  assert.match(page.text(), /AI training course/);
  release({ok: true, json: async () => structuredClone(archived)});
  await page.flush();
  assert.match(page.text(), /AI training course/);
  assert.doesNotMatch(page.text(), /READ-ONLY TRANSACTION/);
});
