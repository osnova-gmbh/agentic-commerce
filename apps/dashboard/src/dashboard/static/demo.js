'use strict';

const checkout = document.getElementById('checkout-content');
const checkoutStatus = document.getElementById('status');
let catalogServices = [];
let checkoutState = null;
let checkoutMode = 'auto';
let selectedService = null;
let draftInputs = {};
let checkoutBusy = false;
let checkoutError = '';
let checkoutSignature = '';
let checkoutPinnedView = null;
let checkoutPinnedError = '';
let checkoutRefreshId = 0;
let providerOffers = [];
let providerOffersLoaded = false;
let providerOffersError = '';
const pendingKeys = new Map();

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
  history.replaceState(null, '', location.pathname + location.search);
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
  return '/demo?company=' + encodeURIComponent(offer.company_id) + '&offer=' + encodeURIComponent(offer.offer_id);
}

function providerPrice(offer) {
  return el('div', 'service-price',
    el('strong', '', offer.price_label || 'Request quote'),
    offer.pricing_basis ? el('small', '', offer.pricing_basis) : null);
}

function providerCard(offer) {
  return el('article', 'service-card',
    el('div', 'service-card-top', pill('', '', offer.category || 'Business service'),
      el('span', 'mini-code', offer.availability === 'waitlist' ? 'WAITLIST' : 'PROVIDER OFFER')),
    el('h3', '', offer.title), el('p', 'service-seller', offer.company_name),
    el('p', 'service-description', offer.description),
    el('div', 'service-card-bottom', providerPrice(offer), providerLink('View offering', providerOfferUrl(offer))));
}

function providerDetail(offer) {
  const actions = el('div', 'checkout-actions');
  if (offer.contact_url) actions.append(providerLink(offer.availability === 'waitlist' ? 'Join waitlist' : 'Request quote',
    offer.contact_url, false, true));
  actions.append(providerLink('Official details', offer.source_url, true, true),
    checkoutNavigation('All provider offers', showCatalog));
  return el('div', '',
    checkoutHeading(offer.company_name, offer.title, offer.description),
    el('div', 'order-details',
      el('div', 'order-service', el('span', 'eyebrow', 'PUBLISHED PROVIDER PRICING'), providerPrice(offer),
        el('p', '', offer.availability === 'waitlist' ? 'Availability: waitlist' : 'Contact the provider to confirm scope and availability.')),
      el('div', 'order-service', el('span', 'eyebrow', 'BEFORE A DEAL'),
        el('p', '', 'Provider pricing is not an agreed escrow amount. Request a quote to confirm the deliverables, payment terms and any subscription or usage charges.'))),
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
        'Actual products and services, with their published pricing or an official route to request a quote.'),
      list, providerLink('Demo transaction history', '/', true));
  }
  const signature = JSON.stringify({companyId, offerId, offers, loaded: providerOffersLoaded, error: providerOffersError});
  if (signature !== checkoutSignature) {
    checkoutSignature = signature; checkout.replaceChildren(content);
  }
  checkoutStatus.className = 'demo-status' + (providerOffersError ? ' error' : '');
  checkoutStatus.textContent = providerOffersError ||
    'Published provider offerings. A quote is required before a new escrow deal can be agreed.';
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
  for (const [name, field] of Object.entries(service.input_schema.properties || {})) draftInputs[name] = field.default || (name === 'topic' ? 'Agentic commerce' : '');
  checkoutSignature = '';
  renderCheckout(checkoutState);
}

function catalogView() {
  const list = el('div', 'service-grid', ...catalogServices.map(service => {
    const button = checkoutButton('Select service', () => chooseService(service));
    button.setAttribute('aria-label', 'Select ' + service.title);
    const pending = checkoutState?.order && !['SETTLED', 'REFUNDED', 'CANCELLED', 'EXPIRED'].includes(checkoutState.state);
    button.disabled ||= Boolean(pending);
    return el('article', 'service-card',
      el('div', 'service-card-top', pill('', '', service.category), el('span', 'mini-code', 'DEMO SERVICE')),
      el('h3', '', service.title), el('p', 'service-seller', service.seller_name),
      el('p', 'service-description', service.description),
      el('div', 'service-files', ...service.deliverable.required_files.map(file => el('span', '', file))),
      el('div', 'service-card-bottom', el('div', 'service-price', el('strong', '', moneyText(service.price)), el('small', '', 'Fixed demo price')), button));
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
  const submit = checkoutButton('Review terms', () => {}); submit.type = 'submit';
  const form = el('form', 'service-form', fields, el('div', 'checkout-actions', submit, checkoutButton('Back to services', showCatalog, true)));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    mutateCheckout('/api/demo/orders', { seller_org_id: service.seller_org_id, offer_id: service.offer_id, inputs: draftInputs });
  });
  return el('div', '', checkoutHeading('YOUR SERVICE', service.title, service.description),
    el('div', 'selected-service-line', el('span', '', service.seller_name), el('strong', '', moneyText(service.price))), form);
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
  const intro = titles[stage] || ['AGENTS AT WORK', 'Preparing your selected service.', 'The agents are exchanging signed messages. You can follow their progress below.'];
  const details = el('div', 'order-details',
    el('div', 'order-service', el('span', 'eyebrow', 'SELECTED SERVICE'), el('h3', '', service.title), el('p', '', service.seller_name),
      ...Object.entries(inputs).map(([name, value]) => el('p', 'order-input', el('span', '', (service.input_schema.properties[name]?.title || name) + ': '), value)),
      el('div', 'service-files', ...service.deliverable.required_files.map(file => el('span', '', file)))),
    el('dl', 'order-totals', ...[
      ['Total to escrow', payment.price], ['Seller receives', payment.payout], ['Operator fee', payment.fee],
    ].map(([label, value]) => el('div', '', el('dt', '', label), el('dd', '', moneyText(value))))));
  const actions = el('div', 'checkout-actions');
  const path = '/api/demo/orders/' + encodeURIComponent(state.deal_id);
  if (state.running || checkoutBusy) {
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
  let mode = checkoutMode;
  if (mode === 'auto') mode = checkoutMode = state.order ? 'order' : 'catalog';
  const signature = JSON.stringify({ mode, state: mode === 'configure' ? null : state, selected: selectedService?.offer_id, busy: checkoutBusy });
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
    const next = await checkoutJSON('/api/demo/status', { cache: 'no-store' });
    const selectedId = pinned();
    let selected = null, selectionError = '';
    if (selectedId && selectedId !== next.deal_id) {
      try {
        selected = await checkoutJSON('/api/deals/' + encodeURIComponent(selectedId), { cache: 'no-store' });
      } catch (error) {
        selectionError = 'Cannot load selected deal: ' + error.message;
      }
    }
    if (requestId !== checkoutRefreshId || selectedId !== pinned()) return;
    const changed = next.state !== checkoutState?.state || next.deal_id !== checkoutState?.deal_id;
    checkoutState = next;
    checkoutPinnedView = selected; checkoutPinnedError = selectionError;
    if (changed) await refresh();
    if (requestId !== checkoutRefreshId || selectedId !== pinned()) return;
    renderCheckout(checkoutState);
  } catch (error) {
    checkoutStatus.className = 'demo-status error'; checkoutStatus.textContent = 'Cannot load checkout: ' + error.message;
  }
}

async function pollCheckout() { await refreshCheckout(); setTimeout(pollCheckout, 1000); }
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
});
pollCheckout();
