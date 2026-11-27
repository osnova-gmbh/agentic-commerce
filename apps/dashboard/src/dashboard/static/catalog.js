'use strict';

const grid = document.getElementById('companies');
const search = document.getElementById('company-search');
const priorityOnly = document.getElementById('priority-only');
const status = document.getElementById('catalog-status');
let companies = [];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function section(title, text) {
  const block = element('section', 'company-section');
  block.append(element('h4', '', title), element('p', '', text));
  return block;
}

function listedOffers(company) {
  return (Array.isArray(company.offers) ? company.offers : [])
    .filter(offer => offer && typeof offer.offer_id === 'string' && offer.offer_id && offer.title);
}

function offerPrice(offer) {
  if (offer.availability === 'waitlist') return 'Waitlist';
  if (offer.price_label === 'Request quote') return 'Price on request';
  if (typeof offer.price_label === 'string' && offer.price_label.trim()) return offer.price_label;
  if (typeof offer.price_minor === 'number' && Number.isFinite(offer.price_minor) && offer.currency) {
    try {
      return new Intl.NumberFormat('en-GB', { style: 'currency', currency: offer.currency })
        .format(offer.price_minor / 100);
    } catch {}
  }
  return 'Price on request';
}

function offerList(company) {
  const block = element('section', 'company-offers-section');
  block.append(element('h4', '', 'Offers'));
  const offers = listedOffers(company);
  if (!offers.length) {
    block.append(element('p', 'company-offers-empty', 'Offer details are not yet available.'));
    return block;
  }
  const list = element('ul', 'company-offers');
  list.setAttribute('aria-label', company.name + ' offers');
  for (const offer of offers) {
    const link = element('a', 'company-offer');
    const selection = new URLSearchParams({
      checkout: '1',
      company: offer.company_id || company.org_id,
      offer: offer.offer_id,
    });
    link.href = '/demo?' + selection.toString();
    link.setAttribute('aria-label', 'View ' + offer.title + ' from ' + company.name);
    const heading = element('div', 'company-offer-heading');
    const arrow = element('span', 'company-offer-arrow', '→');
    arrow.setAttribute('aria-hidden', 'true');
    heading.append(element('strong', '', offer.title), arrow);
    const bottom = element('div', 'company-offer-bottom');
    bottom.append(
      element('span', 'company-offer-price', offerPrice(offer)),
      element('span', 'company-offer-action', 'View deal')
    );
    link.append(heading);
    if (offer.description) link.append(element('p', '', offer.description));
    link.append(bottom);
    if (offer.pricing_basis) link.append(element('p', 'company-offer-basis', offer.pricing_basis));
    const item = element('li');
    item.append(link);
    list.append(item);
  }
  block.append(list);
  return block;
}

function card(company) {
  const node = element('article', 'company-card' + (company.recommended ? ' recommended' : ''));
  const heading = element('div', 'company-card-head');
  const name = element('div');
  name.append(
    element('span', 'prospect-badge', company.recommended ? 'First to approach' : 'Campus company'),
    element('h3', '', company.name)
  );
  heading.append(name);
  if (company.outreach_priority) heading.append(element('span', 'company-rank', String(company.outreach_priority).padStart(2, '0')));
  const foot = element('div', 'company-card-foot');
  foot.append(element('span', '', company.campus || 'Campus company'));
  const dealsLink = element('a', '', 'View deals');
  dealsLink.href = '/demo?' + new URLSearchParams({ company: company.org_id }).toString();
  dealsLink.setAttribute('aria-label', 'View deals from ' + company.name);
  foot.append(dealsLink);
  const audience = section('Who they serve', company.target_customers);
  audience.classList.add('company-audience');
  node.append(heading, section('What they provide', company.products_and_services),
    offerList(company), audience, foot);
  return node;
}

function render() {
  const query = search.value.trim().toLocaleLowerCase();
  const shown = companies.filter(company =>
    (!priorityOnly.checked || company.recommended) &&
    [company.name, company.products_and_services, company.target_customers,
      ...(Array.isArray(company.categories) ? company.categories : []),
      ...listedOffers(company).flatMap(offer => [offer.title, offer.description, offer.category])]
      .join(' ').toLocaleLowerCase().includes(query)
  );
  grid.replaceChildren(...shown.map(card));
  document.getElementById('company-count').textContent = '(' + companies.length + ')';
  const offers = shown.reduce((count, company) => count + listedOffers(company).length, 0);
  status.textContent = shown.length
    ? 'Showing ' + shown.length + ' of ' + companies.length + ' companies · ' + offers + ' provider offers.'
    : 'No companies match. Try another search or show all prospects.';
}

search.addEventListener('input', render);
priorityOnly.addEventListener('change', render);

async function load() {
  try {
    const response = await fetch('/api/catalog', { cache: 'no-store' });
    if (!response.ok) throw new Error('The catalog could not be loaded.');
    const body = await response.json();
    companies = body.companies.filter(company =>
      company.status === 'prospective_buyer' || listedOffers(company).length
    );
    render();
  } catch (error) {
    status.textContent = error.message || 'The catalog could not be loaded. Refresh to retry.';
  }
}
load();
