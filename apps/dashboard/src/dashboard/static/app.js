'use strict';

// Both the read-only dashboard and local demo share this workspace and live API.
const isDemo = document.body.dataset.mode === 'demo';
function isLegacyCheckout() { return isDemo && new URLSearchParams(location.search).get('legacy') === '1'; }
function isProviderView() { return isDemo && !isLegacyCheckout() && !pinned(); }
document.getElementById('app').innerHTML = `
  <a class="skip-link" href="#deal">Skip to the selected deal</a>
  <header class="site-header wrap">
    <a class="brand" href="${isDemo ? '/demo' : '/'}" aria-label="Cogit Finance home">
      <img src="/static/assets/mark.svg" width="31" height="31" alt="">
      <span>cogit<span class="brand-divider">/</span><span class="brand-finance">finance</span></span>
    </a>
    <nav aria-label="Workspace navigation">${isDemo ? '<a href="#demo-controls" id="browse-services-nav">Services</a>' : ''}<a class="nav-current" href="#workspace" aria-current="page">Deal overview</a><a href="/catalog">Company catalog</a>${isDemo ? '<a href="/">Demo history</a>' : '<a href="#activity">Activity</a>'}</nav>
    <span class="environment"><span class="status-dot"></span>${isDemo ? 'Local simulation' : 'Read-only workspace'}</span>
  </header>
  <section class="workspace-intro wrap" aria-labelledby="page-heading">
    <div><p class="eyebrow">A CLEAR VIEW OF EVERY DEAL</p><h1 id="page-heading">Trust, from start to <span>settlement.</span></h1><p class="intro-copy">The terms, the work, the payment. All in one place.</p></div>
    <div class="connection"><span id="live" class="live" role="status">Connecting</span><span class="connection-note">${isDemo ? 'Real agent flow. Simulated funds.' : 'Every step on record.'}</span></div>
  </section>
  <main class="workspace wrap" id="workspace">
    <div class="workspace-chrome"><span class="chrome-location"><span class="window-dots" aria-hidden="true"><i></i><i></i><i></i></span>cogit finance <span class="chrome-slash">/</span> operator workspace</span><span class="chrome-mode">${isDemo ? 'INTERACTIVE DEMO' : 'DEAL MONITOR'}</span></div>
    <div class="workspace-layout">
      <aside id="deal-history-sidebar" class="workspace-sidebar" aria-label="Demo history and participants">
        <div class="campus"><span class="campus-icon">D</span><div><strong>Delta Campus</strong><span>Operator workspace</span></div></div>
        <div class="sidebar-selection"><span aria-hidden="true">▦</span> Deal overview <span id="deal-count">00</span></div>
        <div class="sidebar-heading"><h2>YOUR DEALS</h2><button id="follow" type="button" hidden>Follow newest</button></div>
        <ul id="deal-list"><li class="sidebar-empty">Loading deals…</li></ul>
        <p class="sidebar-label">DEAL PARTICIPANTS</p><div id="participants"><p class="sidebar-empty">Select a deal to see its participants.</p></div>
        <div class="sidebar-foot"><span class="status-dot"></span><div>Proof before payment.<br><span>EUR · 1% operator fee</span></div></div>
      </aside>
      <div class="workspace-content">
        <section id="demo-controls" class="checkout-shell" aria-label="Service catalog and checkout" ${isDemo ? '' : 'hidden'}>
          <div id="checkout-content"><p class="eyebrow">SERVICE CATALOG</p><h2>Choose the work. Set the terms.</h2></div>
          <p id="status" class="demo-status" role="status">Loading available services…</p>
        </section>
        <div id="deal" tabindex="-1"><div class="empty-state"><p class="eyebrow">YOUR DEAL WORKSPACE</p><h2>Getting everything in view.</h2><p>Loading deals and payment activity…</p></div></div>
      </div>
    </div>
  </main>
  <footer class="site-footer wrap"><span>Independent agents. Shared terms. One clear outcome.</span><span>COGIT FINANCE <span class="footer-dot">·</span> ${isDemo ? 'DEMO ENVIRONMENT' : 'OPERATOR VIEW'}</span></footer>
`;

const ICONS = {
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  cross: ['M6.5 6.5l11 11', 'M17.5 6.5l-11 11'],
  lock: ['M6 11h12v9H6z', 'M8.5 11V8a3.5 3.5 0 0 1 7 0v3'],
  clock: ['M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z', 'M12 8v4.5l3 2'],
  dash: ['M7 12h10'],
  document: ['M6 3h8l4 4v14H6z', 'M14 3v5h5', 'M9 12h6', 'M9 16h6'],
  shield: ['M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z', 'M8 12l3 3 5-6'],
};
const OUTCOMES = { pass: ['done', 'check', 'Passed'], fail: ['failed', 'cross', 'Failed'], error: ['failed', 'cross', 'Error'], waiting: ['active', 'clock', 'Pending'], none: ['', 'dash', 'No verdict'] };
const CHECK_NAMES = { integrity: 'Artifact integrity', 'required-files': 'Required files', deadline: 'Delivery deadline' };
const EVENT_NAMES = { service_request: 'Purchase requested', quote: 'Quote received', terms_proposed: 'Terms proposed', accept_terms: 'Terms accepted', terms_countersigned: 'Agreement signed', payment_request: 'Funding requested', funding_received: 'Funds held in escrow', delivery: 'Work delivered', evaluation_requested: 'Checks requested', verdict: 'Evaluator verdict', decision: 'Delivery decision', payout_submitted: 'Payout submitted', payout_confirmed: 'Payment settled', receipt: 'Receipt issued' };
const shown = {};
let refreshId = 0;

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children) {
    if (child === null || child === undefined || child === '') continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function icon(name, size = 18) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', size); svg.setAttribute('height', size);
  svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
  for (const d of ICONS[name]) { const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', d); svg.append(path); }
  return svg;
}

function pill(tone, iconName, text) { return el('span', 'pill ' + tone, iconName ? icon(iconName, 12) : null, text); }
function moneyText(value) { return String(value || '—').replace(/EUR\s/g, '€'); }
function offerName(deal) { return deal.offer_title || deal.offer_id; }
function pinned() { try { return decodeURIComponent(location.hash.slice(1)); } catch { return ''; } }
async function getJSON(url) { const response = await fetch(url, { cache: 'no-store' }); if (!response.ok) throw new Error(url + ' answered ' + response.status); return response.json(); }

function renderList({ deals, selected, pin }) {
  document.getElementById('follow').hidden = !pin;
  document.getElementById('deal-count').textContent = String(deals.length).padStart(2, '0');
  const items = deals.map(deal => {
    const button = el('button', 'deal-item' + (deal.deal_id === selected ? ' selected' : ''),
      el('span', 'deal-item-top', el('span', 'deal-item-title', offerName(deal)), el('span', 'deal-item-price', moneyText(deal.price))),
      el('span', 'deal-item-parties', deal.buyer_org_id + ' → ' + deal.seller_org_id),
      el('span', 'deal-item-bottom', pill(deal.tone, '', deal.state), el('span', 'mini-code', deal.updated_time)));
    button.type = 'button'; button.title = deal.deal_id; button.setAttribute('aria-pressed', String(deal.deal_id === selected));
    button.addEventListener('click', () => { location.hash = encodeURIComponent(deal.deal_id); });
    return el('li', '', button);
  });
  if (!items.length) items.push(el('li', 'sidebar-empty', 'Your first deal will appear here.'));
  document.getElementById('deal-list').replaceChildren(...items);
}

function renderParticipants(view) {
  const target = document.getElementById('participants');
  if (!view) { target.replaceChildren(el('p', 'sidebar-empty', 'Participants appear when a deal starts.')); return; }
  const { deal } = view;
  target.replaceChildren(...[
    ['buyer', deal.buyer_org_id, 'Buyer agent', 'B'], ['seller', deal.seller_org_id, 'Seller agent', 'S'],
    ['evaluator', 'Independent checks', 'Evaluator agents', icon('shield', 16)],
  ].map(([role, name, label, initial]) => el('div', 'participant', el('span', 'participant-dot ' + role, initial), el('div', '', el('strong', '', name), el('span', '', label)))));
}

function renderHead(view) {
  const { deal, attempts } = view;
  const right = el('div', 'deal-heading-actions', pill(deal.tone, '', deal.state));
  if (isDemo && attempts.length) {
    const download = el('a', 'text-link', 'Download delivery ', el('span', '', '↗'));
    download.id = 'download'; download.href = '/api/demo/deals/' + encodeURIComponent(deal.deal_id) + '/delivery'; right.append(download);
  }
  return el('header', 'deal-heading', el('div', '',
    el('p', 'eyebrow deal-reference', 'DEAL ' + deal.deal_id.slice(0, 8).toUpperCase()), el('h2', '', offerName(deal)),
    el('p', 'deal-parties', deal.buyer_org_id, el('span', 'party-arrow', '→'), deal.seller_org_id)), right);
}

function renderMetrics(view) {
  const { deal, money, steps } = view;
  const held = money.tiles.find(tile => tile.key === 'held'); const seller = money.tiles.find(tile => tile.key === 'seller'); const fee = money.tiles.find(tile => tile.key === 'fee');
  const agreed = steps.find(step => step.key === 'confirm')?.status === 'done';
  return el('section', 'metrics',
    el('div', 'metric', el('span', '', 'Deal value'), el('strong', '', moneyText(deal.price)), el('small', '', deal.price_minor == null ? 'Waiting for agreed terms' : agreed ? 'Agreed by both agents' : 'Awaiting both signatures')),
    el('div', 'metric escrow-metric', el('span', '', 'Held in escrow'), el('strong', '', moneyText(held.display)), el('small', '', money.phase === 'released' ? 'Released after approval' : deal.state === 'APPROVED' && isDemo ? 'Awaiting your release' : money.phase === 'held' ? 'Protected until the checks pass' : 'Awaiting buyer funding')),
    el('div', 'metric', el('span', '', 'Paid to seller'), el('strong', '', moneyText(seller.display)), el('small', '', fee.amount_minor ? moneyText(fee.display) + ' operator fee' : 'Payment follows approved delivery')));
}

function renderSteps(steps) {
  return el('ol', 'lifecycle', ...steps.map(step => {
    const mark = step.status === 'done' ? icon('check', 12) : step.status === 'failed' ? icon('cross', 12) : String(step.n).padStart(2, '0');
    const item = el('li', 'stage ' + step.status, el('span', 'stage-number', mark), el('span', 'stage-title', step.label), el('span', 'stage-note', step.note));
    item.setAttribute('aria-label', 'Step ' + step.n + ', ' + step.label + ': ' + step.status);
    if (step.status === 'active') item.setAttribute('aria-current', 'step'); return item;
  }));
}

function renderBanner(money, state) {
  const phase = money.phase;
  const label = phase === 'released' ? 'PAYMENT COMPLETE' : phase === 'held' ? 'FUNDS PROTECTED' : 'DEAL IN PROGRESS';
  return el('section', 'settlement-banner ' + phase,
    el('span', 'banner-icon', icon(phase === 'released' ? 'check' : phase === 'held' ? 'lock' : 'clock', 21)),
    el('div', '', el('p', 'eyebrow', label), el('h3', '', moneyText(money.headline)), el('p', 'banner-detail', isDemo && state === 'APPROVED' ? 'All checks passed. Funds stay in escrow until you choose to release payment.' : moneyText(money.detail))));
}

function renderVerdicts(attempts) {
  const latest = attempts.at(-1); const count = latest?.verdicts.filter(v => v.outcome === 'pass').length || 0;
  const section = el('section', 'panel checks-panel', el('div', 'panel-heading', el('div', '', el('p', 'eyebrow', 'PROOF OF DELIVERY'), el('h3', '', 'Independent checks')), latest ? el('span', 'mini-code', count + ' / ' + latest.verdicts.length + ' PASSED') : icon('shield', 20)));
  if (!attempts.length) section.append(el('div', 'panel-empty', icon('shield', 24), el('p', '', 'Ready when the work is.', el('span', '', 'Evaluators check the files, integrity, and delivery deadline.'))));
  for (const attempt of attempts) {
    const decision = attempt.decision === 'approve' ? pill('done', 'check', 'Approved') : attempt.decision === 'reject' ? pill('failed', 'cross', 'Rejected') : pill('active', 'clock', 'Evaluating');
    const rows = attempt.verdicts.map(verdict => {
      const [tone, iconName, label] = OUTCOMES[verdict.outcome] || ['', 'dash', verdict.outcome];
      return el('li', 'check-item', el('span', 'check-icon ' + tone, icon(iconName, 15)),
        el('div', 'check-copy', el('strong', '', CHECK_NAMES[verdict.evaluator] || verdict.evaluator), el('p', '', verdict.reasons.join('; ') || (verdict.outcome === 'waiting' ? 'Waiting for the evaluator.' : verdict.outcome === 'none' ? 'No verdict recorded for this attempt.' : 'Check complete.'))), pill(tone, '', label));
    });
    section.append(el('div', 'attempt', el('div', 'attempt-heading', el('span', '', 'Delivery ' + String(attempt.attempt).padStart(2, '0')), decision, el('time', 'mini-code', attempt.delivered_at + ' UTC')), el('ul', 'check-list', ...rows)));
  }
  return section;
}

function renderAccounts(accounts) {
  const section = el('section', 'bank-panel', el('div', 'panel-heading', el('div', '', el('p', 'eyebrow', 'THE PAYMENT RAIL'), el('h3', '', 'Bank accounts')), icon('lock', 19)));
  if (accounts === null) section.append(el('p', 'bank-empty', 'The bank is not reachable.'));
  else if (!accounts.length) section.append(el('p', 'bank-empty', 'No bank connected.'));
  else section.append(el('ul', 'account-list', ...accounts.map(account => el('li', 'account',
    el('div', 'account-top', el('span', '', account.owner), el('strong', '', moneyText(account.balance))), el('span', 'account-iban', account.iban)))));
  section.append(el('p', 'bank-note', el('span', 'status-dot'), 'Simulated bank · EUR')); return section;
}

function renderEvents(timeline) {
  const headers = ['#', 'Event', 'Agent', 'State after', 'Hash', 'Time (UTC)'];
  const table = el('table', 'events', el('thead', '', el('tr', '', ...headers.map(text => el('th', '', text)))),
    el('tbody', '', ...timeline.map(row => {
      const actor = el('td', 'event-actor', el('span', 'actor-dot ' + row.actor, row.actor.slice(0, 1).toUpperCase()), row.actor); actor.title = row.actor_did;
      return el('tr', row.tone, el('td', 'event-seq', String(row.seq).padStart(2, '0')),
        el('td', 'event-name', el('strong', '', EVENT_NAMES[row.event_type] || row.event_type), el('span', '', row.detail || row.event_type)), actor,
        el('td', 'mini-code event-state', row.state_after), el('td', 'mini-code', row.hash8), el('td', 'mini-code', row.time));
    })));
  const section = el('section', 'activity-panel', el('div', 'panel-heading', el('div', '', el('p', 'eyebrow', 'NOTHING IN THE DARK'), el('h3', '', 'Deal activity')), el('span', 'activity-count', timeline.length + ' events on record')), el('div', 'table-scroll', table));
  section.id = 'activity'; return section;
}

function renderDeal({ view, accounts }) {
  const main = document.getElementById('deal');
  if (!view) {
    const placeholder = el('section', 'empty-state', el('span', 'empty-icon', icon('document', 30)), el('p', 'eyebrow', 'GOOD WORK STARTS WITH CLEAR TERMS'), el('h2', '', 'Your next deal starts here.'),
      el('p', '', isDemo ? 'Select a service from the catalog above. Review the terms, fund escrow, and follow the delivery.' : 'A deal appears here when a buyer sends a service request.'),
      el('div', 'empty-principles', el('span', '', icon('lock', 15), 'Funds held safely'), el('span', '', icon('shield', 15), 'Work independently checked')));
    placeholder.id = 'activity'; main.replaceChildren(placeholder); return;
  }
  main.replaceChildren(renderHead(view), renderMetrics(view), renderSteps(view.steps), renderBanner(view.money, view.deal.state), el('div', 'evidence-grid', renderVerdicts(view.attempts), renderAccounts(accounts)), renderEvents(view.timeline));
}

function render(key, data, draw) { const signature = JSON.stringify(data); if (shown[key] !== signature) { shown[key] = signature; draw(data); } }
function syncWorkspaceMode() {
  const providers = isProviderView();
  const history = isDemo && !isLegacyCheckout() && Boolean(pinned());
  document.getElementById('deal-history-sidebar').hidden = providers;
  document.querySelector('.workspace-layout').style.gridTemplateColumns = providers ? 'minmax(0, 1fr)' : '';
  document.getElementById('deal').hidden = providers;
  if (isDemo) {
    document.getElementById('page-heading').innerHTML = providers ? 'Services from <span>Delta Campus companies.</span>' :
      history ? 'Demo transaction <span>history.</span>' : 'Trust, from start to <span>settlement.</span>';
    document.querySelector('.intro-copy').textContent = providers ? 'Explore their actual products, published pricing and official contact options.' :
      history ? 'A saved simulated transaction. Provider offers are available under Services.' : 'The terms, the work, the payment. All in one place.';
    document.querySelector('.connection-note').textContent = providers ? 'Published products and services.' :
      history ? 'Saved simulated transaction.' : 'Real agent flow. Simulated funds.';
    document.querySelector('.environment').innerHTML = '<span class="status-dot"></span>' +
      (providers ? 'Provider directory' : history ? 'Demo history' : 'Local simulation');
  }
}

async function refresh() {
  const id = ++refreshId;
  syncWorkspaceMode();
  if (isProviderView()) return;
  const deals = (await getJSON('/api/deals')).deals; const pin = pinned(); const known = deals.some(deal => deal.deal_id === pin); const selected = pin ? (known ? pin : '') : deals.length ? deals[0].deal_id : '';
  const [view, accounts] = await Promise.all([selected ? getJSON('/api/deals/' + encodeURIComponent(selected)) : null, getJSON('/api/accounts').then(body => body.accounts, () => null)]);
  if (id !== refreshId) return;
  render('list', { deals, selected, pin: known }, renderList); render('deal', { view, accounts }, renderDeal); render('participants', view ? view.deal : null, () => renderParticipants(view));
}

async function loop() {
  const live = document.getElementById('live');
  try { await refresh(); live.className = 'live ok'; live.textContent = 'Live · updated ' + new Date().toLocaleTimeString('en-GB'); }
  catch { live.className = 'live lost'; live.textContent = 'Connection lost · retrying'; }
  setTimeout(loop, 1000);
}

document.getElementById('follow').addEventListener('click', () => { history.replaceState(null, '', location.pathname + location.search); refresh().catch(() => {}); });
// Section navigation must keep the selected deal's ID in the URL.
document.querySelectorAll('a[href="#workspace"], a[href="#activity"], a[href="#deal"]').forEach(link => {
  link.addEventListener('click', event => {
    const target = document.getElementById(link.getAttribute('href').slice(1));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView();
    if (target.id === 'deal') target.focus({ preventScroll: true });
  });
});
window.addEventListener('hashchange', () => { refresh().catch(() => {}); });
loop();
