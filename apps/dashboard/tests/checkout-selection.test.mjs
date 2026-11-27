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

const providerServices = publishedOffers.map(offer => ({
  ...service, seller_org_id: 'seller-co', offer_id: 'provider:' + offer.company_id + ':' + offer.offer_id,
  title: offer.title, seller_name: offer.company_name, description: offer.description,
  provider_company_id: offer.company_id, provider_offer_id: offer.offer_id,
  provider_demo: true, demo: true, published_price_label: offer.price_label,
  published_price_minor: offer.price_minor, price_minor: offer.price_minor,
  pricing_basis: offer.pricing_basis, requires_demo_amount: !offer.price_minor,
  suggested_demo_price_minor: 50000, demo_max_price_minor: 200000,
  input_schema: {properties: {brief: {type: 'string', title: 'Brief', default: 'Team use case'}}, required: ['brief']},
}));

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
  reportValidity() { return true; }
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

async function harness({hash = archivedId, search = '?legacy=1', running = false, state = 'SETTLED', archiveResponse, offers = publishedOffers, services = [service, ...providerServices], currentService = service, orderResponses = {}} = {}) {
  const elements = Object.fromEntries(['checkout-content', 'status', 'demo-controls', 'browse-services-nav']
    .map(id => [id, new Element('div')]));
  const listeners = [];
  let currentHash = hash ? '#' + hash : '';
  const requests = [];
  const current = {
    deal_id: activeId, running, state, error: null,
    order: {service: currentService, inputs: {topic: 'AI for finance teams'}, scenario: 'happy'},
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
    isLegacyCheckout: () => {
      const query = new URLSearchParams(location.search);
      return query.get('legacy') === '1' || query.get('checkout') === '1' || Boolean(query.get('company') && query.get('offer'));
    },
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
      requests.push({url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined});
      if (url === '/api/demo/orders' && options.method === 'POST') {
        const order = JSON.parse(options.body);
        current.order = {service: services.find(item => item.offer_id === order.offer_id), inputs: order.inputs};
        current.state = 'QUOTED'; current.allowed_actions = ['fund'];
        return {ok: true, json: async () => ({deal_id: activeId})};
      }
      if (url === '/api/provider-offers') return {ok: true, json: async () => ({offers})};
      if (url === '/api/demo/services') return {ok: true, json: async () => ({services})};
      if (url === '/api/demo/status') return {ok: true, json: async () => structuredClone(current)};
      if (url.startsWith('/api/demo/orders/')) {
        const id = decodeURIComponent(url.slice('/api/demo/orders/'.length));
        const order = orderResponses[id] || (id === current.deal_id ? current : null);
        if (order) return {ok: true, json: async () => structuredClone(order)};
      }
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
    inputs: () => elements['checkout-content'].querySelectorAll('input'),
    fill: async (id, value) => {
      const input = elements['checkout-content'].querySelectorAll('input').find(node => node.id === id);
      assert.ok(input, 'Missing input: ' + id); input.value = value; input.listeners.input(); await flush();
    },
    submit: async () => {
      const form = elements['checkout-content'].querySelectorAll('form')[0];
      assert.ok(form, 'Missing checkout form'); form.listeners.submit({preventDefault() {}}); await flush();
    },
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
  assert.equal(page.links().find(link => link.textContent === 'View deal').href,
    '/demo?checkout=1&company=elephant&offer=learning-platform');
});

test('a provider deep link opens its purchase form and preserves published billing basis', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations'});
  assert.match(page.text(), /Commerce operations platform/);
  assert.match(page.text(), /Base/);
  assert.match(page.text(), /Monthly subscription, billed annually/);
  assert.match(page.text(), /Simulated escrow amount/);
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Review terms')));
  assert.doesNotMatch(page.text(), /Learning and knowledge platform|AI training course/);
  assert.ok(page.requests.some(request => request.url === '/api/demo/services'));
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('provider checkout has no call or external-contact buttons', async () => {
  const page = await harness({hash: '', search: '?company=elephant&offer=learning-platform'});
  assert.doesNotMatch(page.text(), /Request (call|quote)|Official details|Join waitlist/);
  assert.match(page.text(), /Simulated purchase/);
  assert.ok(page.links().every(link => !link.href.startsWith('https:')));
  assert.equal(page.inputs().find(input => input.id === 'demo-amount').value, '500');
});

test('provider purchase submits the selected offer and explicit simulated amount', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations'});
  await page.fill('demo-amount', '123.45');
  await page.fill('service-brief', 'Automate our fulfillment');
  await page.submit();
  const request = page.requests.find(item => item.method === 'POST');
  assert.equal(request.url, '/api/demo/orders');
  assert.equal(request.body.offer_id, 'provider:base:operations');
  assert.equal(request.body.demo_price_minor, 12345);
  assert.equal(request.body.inputs.brief, 'Automate our fulfillment');
  assert.equal(page.location.hash, '#' + activeId);
  assert.match(page.text(), /Commerce operations platform/);
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Fund escrow')));
});

test('switching selected provider opens that provider without the previous service', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations'});
  page.location.search = '?checkout=1&company=elephant&offer=learning-platform';
  await page.context.refreshCheckout();
  assert.match(page.text(), /Learning and knowledge platform/);
  assert.doesNotMatch(page.text(), /Commerce operations platform|AI training course/);
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
  assert.doesNotMatch(page.text(), /AI training course|Market report/);
  assert.ok(page.buttons().every(button => !/Fund escrow|Review terms/.test(button.textContent)));
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

test('invalid simulated amounts never submit a provider purchase', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations'});
  await page.fill('demo-amount', '12.345');
  await page.submit();
  assert.match(page.status(), /at most two decimal places/);
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('an unrelated pending checkout does not block a provider purchase', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations', state: 'FUNDED'});
  assert.match(page.text(), /Commerce operations platform/);
  assert.doesNotMatch(page.text(), /Finish your current checkout|AI training course/);
  assert.equal(page.buttons().find(button => button.textContent.startsWith('Review terms')).disabled, false);
  assert.equal(page.current.state, 'FUNDED');
  assert.ok(page.requests.every(request => request.method === 'GET'));
});

test('a provider link resumes its pending transaction and pins the live event view', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations',
    state: 'FUNDED', currentService: providerServices[1]});
  assert.equal(page.location.hash, '#' + activeId);
  assert.match(page.text(), /Commerce operations platform/);
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Simulate work')));
});

test('a provider link starts a fresh purchase after its earlier transaction settled', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations',
    state: 'SETTLED', currentService: providerServices[1]});
  assert.equal(page.location.hash, '');
  assert.match(page.text(), /BUY WITH ESCROW/);
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Review terms')));
});

test('another tab changing its order does not disable the selected provider form', async () => {
  const page = await harness({hash: '', search: '?checkout=1&company=base&offer=operations', state: 'FUNDED', running: true});
  assert.equal(page.buttons().find(button => button.textContent.startsWith('Review terms')).disabled, false);
  assert.equal(page.buttons().find(button => button.textContent.startsWith('Back to services')).disabled, false);
  await page.fill('demo-amount', '123.45');
  page.current.state = 'APPROVED';
  await page.context.refreshCheckout();
  assert.equal(page.buttons().find(button => button.textContent.startsWith('Review terms')).disabled, false);
  assert.match(page.text(), /Commerce operations platform/);
  assert.equal(page.inputs().find(input => input.id === 'demo-amount').value, '123.45');
});

test('a pinned order stays actionable after another tab starts a different order', async () => {
  const ownOrder = {
    deal_id: activeId, running: false, state: 'FUNDED', error: null,
    order: {service, inputs: {topic: 'My training order'}, scenario: 'happy'},
    payment: service, allowed_actions: ['deliver'],
  };
  const page = await harness({hash: activeId, state: 'FUNDED', orderResponses: {[activeId]: ownOrder}});
  page.current.deal_id = 'another-tabs-order';
  page.current.order = {service: providerServices[1], inputs: {brief: 'Different order'}};
  page.current.state = 'APPROVED';
  await page.context.refreshCheckout();
  assert.match(page.text(), /My training order|AI training course/);
  assert.doesNotMatch(page.text(), /Commerce operations platform|READ-ONLY TRANSACTION/);
  assert.ok(page.buttons().some(button => button.textContent.startsWith('Simulate work')));
  assert.ok(page.requests.some(request => request.url === '/api/demo/orders/' + activeId));
  assert.equal(page.location.hash, '#' + activeId);
});
