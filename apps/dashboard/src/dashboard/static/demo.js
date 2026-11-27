'use strict';

const checkout = document.getElementById('checkout-content');
const checkoutStatus = document.getElementById('status');
let catalogServices = [];
let checkoutState = null;
let checkoutMode = 'auto';
let selectedService = null;
let draftInputs = {};
let draftDemoAmount = '';
let loadedSelection = '';
let checkoutBusy = false;
let checkoutError = '';
let checkoutSignature = '';
let checkoutPinnedView = null;
let checkoutPinnedError = '';
let checkoutRefreshId = 0;
let providerOffers = [];
let providerOffersLoaded = false;
let providerOffersError = '';
let borisEvidenceRequestId = 0;
let borisEvidenceSignature = '';
let borisEvidenceDealId = null;
const pendingKeys = new Map();

function renderBorisEvidence(report, dealId, error = '', loading = false) {
  const target = document.getElementById('boris-evidence');
  if (!target) return;
  target.hidden = !isLegacyCheckout() && !pinned();
  if (target.hidden) return;
  const records = dealId && Array.isArray(report?.events)
    ? report.events.filter(row => row.deal_id === dealId && (!row.endpoint || row.endpoint === report.endpoint)) : [];
  const liveTransport = ['http', 'browser'].includes(report?.transport_kind);
  const testedTransport = report?.transport_kind === 'test';
  const isLiveRecord = row => liveTransport && ['http', 'browser'].includes(row.transport_kind) && Boolean(row.endpoint) && row.endpoint === report.endpoint;
  const counts = {verified: 0, pending: 0, failed: 0};
  for (const row of records) if (Object.hasOwn(counts, row.status) && (row.status !== 'verified' || isLiveRecord(row))) counts[row.status]++;
  let label = 'Configured · no requests yet', tone = '';
  if (loading) label = 'Checking Boris evidence';
  else if (error || report?.error) { label = 'Evidence unavailable'; tone = 'failed'; }
  else if (report?.mode === 'offline') label = 'Offline · no Boris traffic';
  else if (testedTransport) label = 'Test transport · no live Boris traffic';
  else if (!report?.configured) label = 'Boris not connected';
  else if (!liveTransport) label = 'Transport not verified';
  else if (counts.failed) { label = 'Boris request failed'; tone = 'failed'; }
  else if (counts.pending) { label = 'Waiting for Boris'; tone = 'active'; }
  else if (counts.verified) { label = 'Boris responses matched'; tone = 'done'; }
  const signature = JSON.stringify({report, dealId, error, label});
  if (signature === borisEvidenceSignature) return;
  borisEvidenceSignature = signature;
  borisEvidenceDealId = dealId;
  const heading = el('div', 'boris-evidence-heading',
    el('div', '', el('p', 'eyebrow', 'CONNECTION PROOF'), el('h3', '', 'Boris request evidence')),
    pill(tone, '', label));
  const content = el('div', '', heading);
  if (report?.endpoint) content.append(el('p', 'boris-endpoint mini-code', 'Configured target: ' + report.endpoint));
  if (report?.execution_location === 'local-agent-cores') content.append(el('p', 'checkout-copy', 'Boris validates the request exchange. The buyer, seller and escrow logic runs in this application.'));
  if (error || report?.error) content.append(el('p', 'checkout-copy', error || report.error));
  if (!dealId) content.append(el('p', 'checkout-copy', 'Select or start a deal to view its Boris requests.'));
  else if (loading) content.append(el('p', 'checkout-copy', 'Loading recorded requests for the selected deal.'));
  else if (report?.mode === 'offline') content.append(el('p', 'checkout-copy', 'This deal runs locally. It has no verified Boris requests.'));
  else if (report) {
    content.append(el('p', 'checkout-copy', liveTransport
      ? counts.verified + ' matched responses · ' + counts.pending + ' pending · ' + counts.failed + ' failed. Configuration alone does not count as execution.'
      : 'These records do not establish a live Boris connection.'));
    const agents = [['buyer-agent', 'Buyer'], ['seller-agent', 'Seller'], ['cogit-finance', 'Escrow']];
    content.append(el('div', 'boris-agent-summary', ...agents.map(([id, name]) => {
      const rows = records.filter(row => row.agent_id === id);
      const matched = rows.filter(row => row.status === 'verified' && isLiveRecord(row)).length;
      const failed = rows.filter(row => row.status === 'failed').length;
      const pending = rows.filter(row => row.status === 'pending').length;
      return el('div', '', el('strong', '', name), el('span', '',
        failed ? failed + ' failed' + (matched ? ' · ' + matched + ' matched' : '') : pending ? pending + ' pending' + (matched ? ' · ' + matched + ' matched' : '') : matched ? matched + ' matched' : 'No live proof'));
    })));
    if (records.length) {
      const table = el('table', 'boris-evidence-table',
        el('thead', '', el('tr', '', ...['Agent / message', 'Request', 'Time (UTC)', 'Result'].map(text => el('th', '', text)))),
        el('tbody', '', ...[...records].sort((a, b) => (Date.parse(b.completed_at || b.started_at) || 0) - (Date.parse(a.completed_at || a.started_at) || 0)).map(row => {
          const matched = row.status === 'verified' && isLiveRecord(row);
          const labels = {verified: matched ? 'Response matched' : row.transport_kind === 'test' ? 'Test response matched' : 'Unverified transport', pending: 'Pending', failed: 'Failed'};
          const result = el('td', '', el('span', 'boris-result ' + (matched ? 'verified' : row.status === 'verified' ? '' : row.status || ''), labels[row.status] || 'Unverified'));
          if (row.error) result.append(el('small', '', row.error));
          if (row.status === 'verified' && row.response_sha256) result.append(el('small', 'mini-code', 'Response SHA-256: ' + row.response_sha256));
          return el('tr', '',
            el('td', '', el('strong', '', row.agent_id || 'Unknown agent'), el('small', '', row.type_key || ''), el('small', 'mini-code', row.endpoint || 'Endpoint not recorded')),
            el('td', 'mini-code', row.request_id || row.event_id || '-', row.message_id ? el('small', '', 'Message: ' + row.message_id) : null),
            el('td', 'mini-code', row.completed_at || row.started_at || '-'), result);
        })));
      content.append(el('div', 'table-scroll', table));
    } else content.append(el('p', 'checkout-copy', 'No Boris request has been recorded for this deal at the configured target.'));
    const link = el('a', 'text-link', 'Open evidence JSON');
    link.href = '/api/demo/boris?deal_id=' + encodeURIComponent(dealId);
    content.append(link);
  }
  target.replaceChildren(content);
}

async function refreshBorisEvidence() {
  const target = document.getElementById('boris-evidence');
  if (!target) return;
  if (!isLegacyCheckout() && !pinned()) { target.hidden = true; return; }
  const id = ++borisEvidenceRequestId;
  const dealId = pinned() || checkoutState?.deal_id || '';
  if (dealId !== borisEvidenceDealId) renderBorisEvidence(null, dealId, '', true);
  try {
    const report = await checkoutJSON('/api/demo/boris' + (dealId ? '?deal_id=' + encodeURIComponent(dealId) : ''), {cache: 'no-store'});
    if (id !== borisEvidenceRequestId || dealId !== (pinned() || checkoutState?.deal_id || '')) return;
    renderBorisEvidence(report, dealId);
  } catch (error) {
    if (id !== borisEvidenceRequestId || dealId !== (pinned() || checkoutState?.deal_id || '')) return;
    renderBorisEvidence(null, dealId, 'Cannot load Boris request evidence: ' + error.message);
  }
}

async function checkoutJSON(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : body.message || 'The request could not be completed.');
    error.status = response.status;
    throw error;
  }
  return body;
}

function checkoutButton(label, action, secondary = false) {
  const arrow = el('span', '', secondary ? '←' : '↗');
  arrow.setAttribute('aria-hidden', 'true');
  const button = el('button', 'button ' + (secondary ? 'secondary' : 'dark'), label, arrow);
  button.type = 'button';
  button.disabled = checkoutBusy || Boolean(checkoutState?.running);
  button.addEventListener('click', action);
  return button;
}

function checkoutHeading(kicker, title, description) {
  return el('div', 'checkout-heading', el('p', 'eyebrow', kicker), el('h2', '', title), el('p', 'checkout-copy', description));
}

function checkoutRail(state) {
  const position = { QUOTED: 1, FUNDING_REQUESTED: 1, FUNDED: 2, DELIVERED: 2, EVALUATING: 2, REJECTED: 2, APPROVED: 3, RELEASING: 3, SETTLED: 4 }[state?.state] || 0;
  return el('ol', 'checkout-rail', ...['Select service', 'Fund escrow', 'Work & checks', 'Release payment'].map((title, index) => {
    const stage = index < position ? 'done' : index === position ? 'active' : '';
    return el('li', stage, el('span', '', index < position ? '✓' : String(index + 1).padStart(2, '0')), title);
  }));
}

function showCatalog() {
  if (!isLegacyCheckout()) {
    history.replaceState(null, '', location.pathname);
    checkoutPinnedView = null; checkoutPinnedError = ''; checkoutSignature = '';
    renderProviderOffers();
    refresh().catch(() => {});
    refreshCheckout();
    return;
  }
  checkoutMode = 'catalog'; checkoutError = ''; checkoutSignature = '';
  loadedSelection = ''; selectedService = null;
  history.replaceState(null, '', location.pathname + '?legacy=1');
  checkoutPinnedView = null; checkoutPinnedError = '';
  renderCheckout(checkoutState);
  refresh().catch(() => {});
}

function showCurrentCheckout() {
  if (!checkoutState?.deal_id) return;
  checkoutMode = 'order'; checkoutError = ''; checkoutSignature = '';
  location.hash = encodeURIComponent(checkoutState.deal_id);
  renderCheckout(checkoutState);
}

function checkoutNavigation(label, action) {
  const button = checkoutButton(label, action, true);
  // Viewing a different record or the catalog must not interrupt a running order.
  button.disabled = false;
  return button;
}

function pinnedCheckoutView(dealId) {
  const view = checkoutPinnedView?.deal?.deal_id === dealId ? checkoutPinnedView : null;
  const deal = view?.deal;
  const heading = checkoutHeading('SELECTED DEAL', deal?.offer_title || deal?.offer_id || (checkoutPinnedError ? 'Deal unavailable.' : 'Loading selected deal.'),
    checkoutPinnedError || 'This is the deal selected by your link. Its transaction record is shown below.');
  const content = el('div', '', heading);
  if (deal) {
    content.append(el('div', 'order-details',
      el('div', 'order-service', el('span', 'eyebrow', 'READ-ONLY TRANSACTION'),
        el('h3', '', deal.offer_title || deal.offer_id),
        el('p', '', deal.buyer_org_id + ' → ' + deal.seller_org_id),
        el('p', 'mini-code', deal.deal_id), pill(deal.tone || '', '', deal.state)),
      el('dl', 'order-totals', el('div', '', el('dt', '', 'Deal value'), el('dd', '', moneyText(deal.price))))));
  }
  const actions = el('div', 'checkout-actions', checkoutNavigation('Browse services', showCatalog));
  if (isLegacyCheckout() && checkoutState?.order) actions.append(checkoutNavigation('View current checkout', showCurrentCheckout));
  content.append(actions);
  return content;
}

function providerLink(label, url, secondary = false, external = false) {
  if (!url) return null;
  let parsed;
  try { parsed = new URL(url, location.origin || 'http://localhost'); } catch { return null; }
  if (!['http:', 'https:'].includes(parsed.protocol)) return null;
  const link = el('a', 'button ' + (secondary ? 'secondary' : 'dark'), label);
  link.href = url;
  if (external) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
  return link;
}

function providerOfferUrl(offer) {
  return '/demo?checkout=1&company=' + encodeURIComponent(offer.company_id) + '&offer=' + encodeURIComponent(offer.offer_id);
}

function publishedPriceLabel(service) {
  const label = service.published_price_label || service.price_label;
  return !label || label === 'Request quote' ? 'Price on request' : label;
}

function providerPrice(offer) {
  const price = !offer.price_label || offer.price_label === 'Request quote' ? 'Price on request' : offer.price_label;
  return el('div', 'service-price',
    el('strong', '', offer.availability === 'waitlist' ? 'Waitlist' : price),
    offer.pricing_basis ? el('small', '', offer.pricing_basis) : null);
}

function providerCard(offer) {
  return el('article', 'service-card',
    el('div', 'service-card-top', pill('', '', offer.category || 'Business service'),
      el('span', 'mini-code', offer.availability === 'waitlist' ? 'WAITLIST' : 'PROVIDER OFFER')),
    el('h3', '', offer.title), el('p', 'service-seller', offer.company_name),
    el('p', 'service-description', offer.description),
    el('div', 'service-card-bottom', providerPrice(offer), providerLink('View deal', providerOfferUrl(offer))));
}

function providerDetail(offer) {
  const free = offer.price_minor === 0;
  const actions = el('div', 'checkout-actions', providerLink('Deal overview', '/demo'));
  return el('div', '',
    checkoutHeading(offer.company_name, offer.title, offer.description),
    el('div', 'order-details',
      el('div', 'order-service', el('span', 'eyebrow', 'PUBLISHED PROVIDER PRICING'), providerPrice(offer),
        el('p', '', offer.availability === 'waitlist' ? 'Availability: waitlist' : free ? 'Free self-paced course.' : 'Pricing and billing terms supplied by the provider.'))),
    actions);
}

function renderProviderOffers() {
  const selected = new URLSearchParams(location.search);
  const companyId = selected.get('company'), offerId = selected.get('offer');
  const offers = companyId ? providerOffers.filter(offer => offer.company_id === companyId) : providerOffers;
  let content;
  if (offerId) {
    const offer = offers.find(item => item.offer_id === offerId);
    content = offer ? providerDetail(offer) : el('div', '',
      checkoutHeading('PROVIDER OFFERS', providerOffersLoaded ? 'Offering unavailable.' : 'Loading offering.',
        providerOffersError || 'The selected offering is not in the current provider catalog.'),
      checkoutNavigation('All provider offers', showCatalog));
  } else {
    const list = el('div', 'service-grid', ...offers.map(providerCard));
    if (!offers.length) list.append(el('p', 'checkout-copy', providerOffersError ||
      (providerOffersLoaded ? 'No provider offerings are listed for this selection.' : 'Loading provider offerings.')));
    content = el('div', '',
      checkoutHeading('PROVIDER OFFERS', 'Explore what the companies provide.',
        'Actual products and services, with their published pricing and availability.'),
      list, providerLink('Demo transaction history', '/', true));
  }
  const signature = JSON.stringify({companyId, offerId, offers, loaded: providerOffersLoaded, error: providerOffersError});
  if (signature !== checkoutSignature) {
    checkoutSignature = signature; checkout.replaceChildren(content);
  }
  checkoutStatus.className = 'demo-status' + (providerOffersError ? ' error' : '');
  checkoutStatus.textContent = providerOffersError ||
    'Select a deal to buy it in the escrow demo and follow the transaction.';
}

async function refreshProviderCheckout(requestId) {
  const selectedId = pinned(), selectedQuery = location.search;
  if (selectedId) {
    let selected = null, selectionError = '';
    try { selected = await checkoutJSON('/api/deals/' + encodeURIComponent(selectedId), {cache: 'no-store'}); }
    catch (error) { selectionError = 'Cannot load selected deal: ' + error.message; }
    if (requestId !== checkoutRefreshId || selectedId !== pinned() || selectedQuery !== location.search) return;
    checkoutPinnedView = selected; checkoutPinnedError = selectionError;
    checkout.replaceChildren(checkoutRail(selected?.deal), pinnedCheckoutView(selectedId));
    checkoutStatus.className = 'demo-status' + (selectionError ? ' error' : '');
    checkoutStatus.textContent = selectionError || 'Read-only demo history. This transaction does not represent a current provider offer.';
    return;
  }
  if (!providerOffersLoaded) {
    try {
      providerOffers = (await checkoutJSON('/api/provider-offers', {cache: 'no-store'})).offers;
      providerOffersLoaded = true; providerOffersError = '';
    } catch (error) { providerOffersError = 'Cannot load provider offers: ' + error.message; }
  }
  if (requestId !== checkoutRefreshId || pinned() || selectedQuery !== location.search) return;
  renderProviderOffers();
}

function chooseService(service) {
  selectedService = service; draftInputs = {}; checkoutMode = 'configure'; checkoutError = '';
  const publishedAmount = service.price_minor;
  const initialAmount = publishedAmount > 0 && publishedAmount <= (service.demo_max_price_minor || Infinity)
    ? publishedAmount : service.suggested_demo_price_minor || 50000;
  draftDemoAmount = service.provider_demo ? String(initialAmount / 100) : '';
  for (const [name, field] of Object.entries(service.input_schema.properties || {})) draftInputs[name] = field.default || (name === 'topic' ? 'Agentic commerce' : '');
  checkoutSignature = '';
  renderCheckout(checkoutState);
}

function checkoutSelection() {
  const query = new URLSearchParams(location.search);
  const company = query.get('company'), offer = query.get('offer');
  return company && offer ? {company, offer, key: company + ':' + offer} : null;
}

function serviceMatchesSelection(service, selection) {
  return service?.provider_company_id === selection.company && service?.provider_offer_id === selection.offer;
}

function unavailableCheckout() {
  return el('div', '', checkoutHeading('SELECTED DEAL', 'Offering unavailable.',
    'The selected offer is not available in the current checkout catalog.'), providerLink('Deal overview', '/demo', true));
}

function catalogView() {
  const list = el('div', 'service-grid', ...catalogServices.map(service => {
    const button = checkoutButton('Select service', () => chooseService(service));
    button.setAttribute('aria-label', 'Select ' + service.title);
    return el('article', 'service-card',
      el('div', 'service-card-top', pill('', '', service.category), el('span', 'mini-code', service.provider_demo ? 'SIMULATED PURCHASE' : 'DEMO SERVICE')),
      el('h3', '', service.title), el('p', 'service-seller', service.seller_name),
      el('p', 'service-description', service.description),
      el('div', 'service-files', ...service.deliverable.required_files.map(file => el('span', '', file))),
      el('div', 'service-card-bottom', el('div', 'service-price', el('strong', '', service.provider_demo ? publishedPriceLabel(service) : moneyText(service.price)), el('small', '', service.provider_demo ? 'Buy in the escrow demo' : 'Fixed demo price')), button));
  }));
  if (!catalogServices.length) list.append(el('p', 'checkout-copy', 'No purchasable services are currently published.'));
  const content = el('div', '', checkoutHeading('SERVICE CATALOG', 'Choose the work you need.', 'Select a published service, review its terms, and fund escrow when you are ready.'), list);
  if (checkoutState?.order) content.append(el('div', 'checkout-actions', checkoutNavigation('View current checkout', showCurrentCheckout)));
  return content;
}

function configureView() {
  const service = selectedService;
  const fields = el('div', 'checkout-fields');
  for (const [name, field] of Object.entries(service.input_schema.properties || {}).sort(([a], [b]) => (a === 'topic' ? -1 : b === 'topic' ? 1 : a.localeCompare(b)))) {
    const input = el('input', 'checkout-input');
    input.id = 'service-' + name; input.name = name;
    input.type = field.type === 'integer' ? 'number' : 'text';
    input.value = draftInputs[name] ?? '';
    input.required = (service.input_schema.required || []).includes(name);
    if (field.maxLength) input.maxLength = field.maxLength;
    if (field.minLength) input.minLength = field.minLength;
    input.addEventListener('input', () => { draftInputs[name] = field.type === 'integer' ? Number(input.value) : input.value; });
    const label = el('label', '', field.title || name.replaceAll('_', ' ')); label.htmlFor = input.id;
    fields.append(el('div', 'checkout-field', label, input));
  }
  if (service.provider_demo) {
    const amount = el('input', 'checkout-input');
    amount.id = 'demo-amount'; amount.name = 'demo_amount'; amount.type = 'number';
    amount.min = '0.01'; amount.step = '0.01'; amount.required = true; amount.value = draftDemoAmount;
    if (service.demo_max_price_minor) amount.max = String(service.demo_max_price_minor / 100);
    amount.addEventListener('input', () => { draftDemoAmount = amount.value; });
    const label = el('label', '', 'Simulated escrow amount (EUR)'); label.htmlFor = amount.id;
    fields.append(el('div', 'checkout-field', label, amount));
  }
  const submit = checkoutButton('Review terms', () => {}); submit.type = 'submit';
  const form = el('form', 'service-form', fields, el('div', 'checkout-actions', submit, checkoutButton('Back to services', showCatalog, true)));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const order = { seller_org_id: service.seller_org_id, offer_id: service.offer_id, inputs: draftInputs };
    if (service.provider_demo) {
      const amount = Number(draftDemoAmount);
      if (!Number.isFinite(amount) || amount <= 0 || Math.abs(amount * 100 - Math.round(amount * 100)) > 0.000001) {
        checkoutError = 'Enter a positive EUR amount with at most two decimal places.';
        checkoutStatus.className = 'demo-status error'; checkoutStatus.textContent = checkoutError; return;
      }
      order.demo_price_minor = Math.round(amount * 100);
    }
    mutateCheckout('/api/demo/orders', order);
  });
  const pricing = service.provider_demo ? el('div', 'order-service',
    el('p', 'eyebrow', 'PUBLISHED PROVIDER OFFER'),
    el('p', '', publishedPriceLabel(service)),
    service.pricing_basis ? el('p', '', service.pricing_basis) : null,
    el('p', 'checkout-copy', 'Simulated purchase. The amount below is for this escrow demonstration; no provider order or real payment is placed.'),
    service.availability === 'waitlist' ? el('p', 'checkout-copy', 'This product is currently waitlisted by the provider.') : null) : null;
  return el('div', '', checkoutHeading('BUY WITH ESCROW', service.title, service.description),
    el('div', 'selected-service-line', el('span', '', service.seller_name), el('strong', '', service.provider_demo ? 'Simulated purchase' : moneyText(service.price))),
    pricing, form);
}

function orderView(state) {
  const { service, inputs } = state.order;
  const payment = state.payment || service;
  const stage = state.state;
  const titles = {
    QUOTED: ['REVIEW THE TERMS', 'Ready to fund escrow.', 'Review the selected service and price. Funding is a separate step; no money has moved yet.'],
    FUNDING_REQUESTED: ['REVIEW THE TERMS', 'Ready to fund escrow.', 'The agents have agreed the terms. Send the exact payment into escrow.'],
    FUNDED: ['FUNDS SECURED', 'Now let the seller do the work.', 'Your payment is held in escrow. Simulate the work and delivery, then let the independent checks run.'],
    REJECTED: ['DELIVERY NEEDS CORRECTION', 'The funds stay in escrow.', 'The first delivery did not pass the checks. Simulate a corrected delivery before payment can be released.'],
    APPROVED: ['DELIVERY APPROVED', 'The work passed. Release payment.', 'All required checks passed. The payment is still held in escrow until you release it to the seller.'],
    SETTLED: ['PAYMENT RELEASED', 'Work delivered. Deal complete.', 'Escrow paid the seller and the operator fee. The delivery and full event record are available below.'],
  };
  const initialFailure = !stage && Boolean(state.error) && !state.running;
  const intro = initialFailure
    ? ['REQUEST BLOCKED', 'The checkout could not start.', 'No terms were agreed and no funds moved. See the recorded request failure below.']
    : titles[stage] || ['AGENTS AT WORK', 'Preparing your selected service.', 'The agents are exchanging signed messages. You can follow their progress below.'];
  const details = el('div', 'order-details',
    el('div', 'order-service', el('span', 'eyebrow', 'SELECTED SERVICE'), el('h3', '', service.title), el('p', '', service.seller_name),
      ...Object.entries(inputs).map(([name, value]) => el('p', 'order-input', el('span', '', (service.input_schema.properties[name]?.title || name) + ': '), value)),
      el('div', 'service-files', ...service.deliverable.required_files.map(file => el('span', '', file))),
      service.provider_demo ? el('p', 'checkout-copy', 'Simulated purchase · ' + publishedPriceLabel(service) + ' published by the provider.') : null),
    el('dl', 'order-totals', ...[
      ['Total to escrow', payment.price], ['Seller receives', payment.payout], ['Operator fee', payment.fee],
    ].map(([label, value]) => el('div', '', el('dt', '', label), el('dd', '', moneyText(value))))));
  const actions = el('div', 'checkout-actions');
  const path = '/api/demo/orders/' + encodeURIComponent(state.deal_id);
  if (initialFailure) {
    const restart = el('a', 'button secondary', 'Return to deals and try a new checkout'); restart.href = '/demo'; actions.append(restart);
  } else if (state.running || checkoutBusy) {
    const label = { prepare: 'Agreeing the service terms…', fund: 'Funding escrow…', deliver: 'Working, delivering and checking…', release: 'Releasing payment…' }[state.action] || 'Processing…';
    const waiting = checkoutButton(label, () => {}); waiting.disabled = true; actions.append(waiting);
  } else if (state.allowed_actions.includes('fund')) {
    actions.append(checkoutButton('Fund escrow', () => mutateCheckout(path + '/fund', {})), el('span', 'action-explainer', moneyText(payment.price) + ' goes to escrow, not directly to the seller.'));
  } else if (state.allowed_actions.includes('deliver')) {
    if (stage === 'FUNDED') {
      const simulation = el('select', 'checkout-select', el('option', '', 'Successful delivery'), el('option', '', 'First delivery fails'));
      simulation.options[0].value = 'happy'; simulation.options[1].value = 'rework'; simulation.id = 'scenario';
      const label = el('label', 'simulation-label', 'Work simulation'); label.htmlFor = 'scenario';
      actions.append(label, simulation, checkoutButton('Simulate work & delivery', () => mutateCheckout(path + '/deliver', { scenario: simulation.value })));
    } else {
      actions.append(checkoutButton('Simulate corrected delivery', () => mutateCheckout(path + '/deliver', { scenario: state.order.scenario })));
    }
  } else if (state.allowed_actions.includes('release')) {
    actions.append(checkoutButton('Release payment to seller', () => mutateCheckout(path + '/release', {})), el('span', 'action-explainer', moneyText(payment.payout) + ' to the seller · ' + moneyText(payment.fee) + ' operator fee.'));
  } else if (stage === 'SETTLED') {
    actions.append(checkoutButton('Browse services', showCatalog), el('span', 'action-explainer', moneyText(payment.payout) + ' paid to the seller.'));
  }
  return el('div', '', checkoutHeading(...intro), details, actions);
}

function renderCheckout(state) {
  if (!state) return;
  const selectedId = pinned();
  if (selectedId && selectedId !== state.deal_id) {
    const selected = checkoutPinnedView?.deal?.deal_id === selectedId ? checkoutPinnedView : null;
    const signature = JSON.stringify({ selectedId, selected, error: checkoutPinnedError, current: state.deal_id });
    if (signature !== checkoutSignature) {
      checkoutSignature = signature;
      checkout.replaceChildren(checkoutRail(selected?.deal), pinnedCheckoutView(selectedId));
    }
    checkoutStatus.className = 'demo-status' + (checkoutPinnedError ? ' error' : '');
    checkoutStatus.textContent = checkoutPinnedError || 'Viewing the selected deal. Your current checkout is preserved.';
    return;
  }
  const selection = checkoutSelection();
  if (selection && !selectedId && !selectedService) {
    checkout.replaceChildren(checkoutRail(null), unavailableCheckout());
    checkoutStatus.textContent = 'The selected deal could not be loaded.';
    return;
  }
  let mode = checkoutMode;
  if (mode === 'auto') mode = checkoutMode = state.order ? 'order' : 'catalog';
  const pendingOrder = state.order && !['SETTLED', 'REFUNDED', 'CANCELLED', 'DECLINED', 'EXPIRED'].includes(state.state)
    ? state.deal_id : null;
  const signature = JSON.stringify({ mode, state: mode === 'configure' ? {pendingOrder} : state, selected: selectedService?.offer_id, busy: checkoutBusy, error: checkoutError });
  if (signature !== checkoutSignature) {
    checkoutSignature = signature;
    checkout.replaceChildren(checkoutRail(mode === 'order' ? state : null), mode === 'configure' ? configureView() : mode === 'order' && state.order ? orderView(state) : catalogView());
  }
  checkoutStatus.className = 'demo-status' + (checkoutError || state.error ? ' error' : state.running ? ' running' : '');
  checkoutStatus.textContent = checkoutError || state.error || (state.running ? 'The agents are processing this step.' : 'Local demo services and simulated payments. No real money moves.');
}

async function mutateCheckout(path, body) {
  if (checkoutBusy) return;
  checkoutBusy = true; checkoutError = '';
  checkout.querySelectorAll('button, input, select').forEach(control => { control.disabled = true; });
  const fingerprint = path + JSON.stringify(body);
  const key = pendingKeys.get(fingerprint) || crypto.randomUUID(); pendingKeys.set(fingerprint, key);
  try {
    const result = await checkoutJSON(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body) });
    pendingKeys.delete(fingerprint); checkoutMode = 'order'; checkoutSignature = '';
    location.hash = encodeURIComponent(result.deal_id);
  } catch (error) {
    checkoutError = error.message;
    if (error.status && error.status < 500) pendingKeys.delete(fingerprint);
  } finally {
    checkoutBusy = false; checkoutSignature = ''; await refreshCheckout();
  }
}

async function refreshCheckout() {
  const requestId = ++checkoutRefreshId;
  if (!isLegacyCheckout()) return refreshProviderCheckout(requestId);
  try {
    if (!catalogServices.length) catalogServices = (await checkoutJSON('/api/demo/services', { cache: 'no-store' })).services;
    const selectedId = pinned(), selectedQuery = location.search;
    const selection = checkoutSelection();
    const current = await checkoutJSON('/api/demo/status', { cache: 'no-store' });
    let next = current;
    let selected = null, selectionError = '';
    if (selectedId && selectedId !== current.deal_id) {
      try {
        next = await checkoutJSON('/api/demo/orders/' + encodeURIComponent(selectedId), { cache: 'no-store' });
      } catch (error) {
        if (error.status !== 404) throw error;
        try {
          selected = await checkoutJSON('/api/deals/' + encodeURIComponent(selectedId), { cache: 'no-store' });
        } catch (archiveError) {
          selectionError = 'Cannot load selected deal: ' + archiveError.message;
        }
      }
    }
    // A new provider checkout must not inherit another tab's active order.
    if (!selectedId && selection && !serviceMatchesSelection(current.order?.service, selection)) {
      next = {running: false, deal_id: null, state: null, order: null, error: null, allowed_actions: []};
    }
    if (requestId !== checkoutRefreshId || selectedId !== pinned() || selectedQuery !== location.search) return;
    const changed = next.state !== checkoutState?.state || next.deal_id !== checkoutState?.deal_id;
    checkoutState = next;
    checkoutPinnedView = selected; checkoutPinnedError = selectionError;
    const activeOrder = next.order && !['SETTLED', 'REFUNDED', 'CANCELLED', 'DECLINED', 'EXPIRED'].includes(next.state);
    if (!selectedId && next.order && ((!selection && checkoutMode === 'auto') ||
      (selection && activeOrder && serviceMatchesSelection(next.order.service, selection)))) {
      location.hash = encodeURIComponent(next.deal_id);
      return;
    }
    if (selection && !selectedId && loadedSelection !== selection.key) {
      loadedSelection = selection.key;
      const service = catalogServices.find(item => serviceMatchesSelection(item, selection));
      if (activeOrder && serviceMatchesSelection(next.order?.service, selection)) {
        selectedService = service || next.order.service; checkoutMode = 'order';
      } else if (service) chooseService(service);
      else { selectedService = null; checkoutMode = 'configure'; }
      checkoutSignature = '';
    }
    if (changed) await refresh();
    if (requestId !== checkoutRefreshId || selectedId !== pinned() || selectedQuery !== location.search) return;
    renderCheckout(checkoutState);
  } catch (error) {
    checkoutStatus.className = 'demo-status error'; checkoutStatus.textContent = 'Cannot load checkout: ' + error.message;
  }
}

async function pollCheckout() { await refreshCheckout(); await refreshBorisEvidence(); setTimeout(pollCheckout, 1000); }
document.getElementById('browse-services-nav')?.addEventListener('click', event => {
  event.preventDefault(); showCatalog(); document.getElementById('demo-controls').scrollIntoView();
});
window.addEventListener('hashchange', () => {
  checkoutMode = 'auto'; checkoutSignature = '';
  checkoutPinnedView = null; checkoutPinnedError = '';
  if (isLegacyCheckout()) renderCheckout(checkoutState);
  else if (!pinned()) renderProviderOffers();
  else {
    checkout.replaceChildren(pinnedCheckoutView(pinned()));
    checkoutStatus.textContent = 'Loading selected demo transaction.';
  }
  refreshCheckout();
  refreshBorisEvidence();
});
pollCheckout();
