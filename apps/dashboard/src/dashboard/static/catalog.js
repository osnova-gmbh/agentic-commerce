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

function card(company) {
  const node = element('article', 'company-card' + (company.recommended ? ' recommended' : ''));
  const heading = element('div', 'company-card-head');
  const name = element('div');
  name.append(
    element('span', 'prospect-badge', company.recommended ? 'First to approach' : 'Buyer prospect'),
    element('h3', '', company.name)
  );
  heading.append(name, element('span', 'company-rank', String(company.outreach_priority).padStart(2, '0')));
  const foot = element('div', 'company-card-foot');
  foot.append(element('span', '', company.campus || 'Campus company'));
  if (company.website) {
    const url = new URL(company.website);
    if (url.protocol === 'https:' || url.protocol === 'http:') {
      const link = element('a', '', 'Visit website ↗');
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.setAttribute('aria-label', 'Visit ' + company.name + ' website');
      foot.append(link);
    }
  }
  node.append(heading, section('What they sell', company.products_and_services),
    section('Who they serve', company.target_customers), foot);
  return node;
}

function render() {
  const query = search.value.trim().toLocaleLowerCase();
  const shown = companies.filter(company =>
    (!priorityOnly.checked || company.recommended) &&
    [company.name, company.products_and_services, company.target_customers, ...company.categories]
      .join(' ').toLocaleLowerCase().includes(query)
  );
  grid.replaceChildren(...shown.map(card));
  document.getElementById('company-count').textContent = '(' + companies.length + ')';
  status.textContent = shown.length
    ? 'Showing ' + shown.length + ' of ' + companies.length + ' prospective buyers.'
    : 'No companies match. Try another search or show all prospects.';
}

search.addEventListener('input', render);
priorityOnly.addEventListener('change', render);

async function load() {
  try {
    const response = await fetch('/api/catalog', { cache: 'no-store' });
    if (!response.ok) throw new Error('The catalog could not be loaded.');
    const body = await response.json();
    companies = body.companies.filter(company => company.status === 'prospective_buyer');
    render();
  } catch (error) {
    status.textContent = error.message || 'The catalog could not be loaded. Refresh to retry.';
  }
}
load();
