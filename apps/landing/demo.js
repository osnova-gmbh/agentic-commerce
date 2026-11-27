// @ts-check
// Illustrative UI only: no bank, AgentDb, identity, or evaluator connection.
/** @typedef {'success' | 'refund'} Scenario */
/** @typedef {{label: string, state: string, held: number, title: string, description: string, event: string}} Stage */
/** @type {Record<Scenario, Stage[]>} */
const scenarios = {
  success: [
    { label: 'Terms agreed', state: 'FUNDING_REQUESTED', held: 0,
      title: 'The research brief is agreed.',
      description: "Northstar's agent commissions Fieldwork's competitor report for €1,250. Both agree on the required files, delivery deadline, and checks.",
      event: 'finance.payment_request' },
    { label: 'Funds held', state: 'FUNDED', held: 125000,
      title: 'Funds are in. Work can begin.',
      description: 'The buyer has funded the deal. Cogit Finance holds the full amount while the seller prepares the delivery.',
      event: 'finance.funding_confirmed' },
    { label: 'Work delivered', state: 'EVALUATING', held: 125000,
      title: 'Delivered. Now independently checked.',
      description: 'The seller submitted the report. Independent evaluators check its integrity, required files, and delivery time.',
      event: 'finance.evaluation_request' },
    { label: 'Checks passed', state: 'RELEASING', held: 125000,
      title: 'The work checks out. Payout is prepared.',
      description: 'All three checks passed. Cogit Finance prepares the seller payout and fee, awaiting bank confirmation.',
      event: 'finance.decision' },
    { label: 'Payment settled', state: 'SETTLED', held: 0,
      title: 'Deal done. Every cent accounted for.',
      description: 'Payment is confirmed. €1,237.50 goes to Fieldwork and €12.50 to the operator. Northstar has its report; neither team has to chase payment.',
      event: 'finance.payout_confirmed' },
  ],
  refund: [
    { label: 'Terms agreed', state: 'FUNDING_REQUESTED', held: 0,
      title: 'A deadline is part of the deal.',
      description: 'Both agents accepted the terms, including the delivery deadline. The buyer has not funded the deal yet.',
      event: 'finance.payment_request' },
    { label: 'Funds held', state: 'FUNDED', held: 125000,
      title: 'Funds are held. The clock is running.',
      description: 'The buyer funded €1,250.00. The seller must submit the agreed deliverable before the deadline.',
      event: 'finance.funding_confirmed' },
    { label: 'Deadline missed', state: 'REFUNDING', held: 125000,
      title: 'No delivery. A refund is prepared.',
      description: 'The delivery deadline passed with no submission. Cogit Finance prepares a full refund, awaiting bank confirmation.',
      event: 'delivery_deadline → refund intent' },
    { label: 'Buyer refunded', state: 'REFUNDED', held: 0,
      title: 'The buyer gets the full amount back.',
      description: 'The €1,250.00 refund is confirmed. Northstar gets its full budget back. Fieldwork receives nothing and no operator fee is charged.',
      event: 'finance.refund_confirmed' },
  ],
};

/** @type {Scenario} */
let scenario = 'success';
let step = 0;
/** @type {number | null} */
let playbackTimer = null;
const stepDurationMs = 6000;
const priceMinor = 125000;
const feeBps = 100;
const feeMinor = Math.floor((priceMinor * feeBps + 5000) / 10000);
const euro = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' });
/** @param {number} minor @returns {string} */
const money = (minor) => euro.format(minor / 100);
/** @param {string} id @returns {HTMLElement} */
function element(id) {
  const node = document.getElementById(id);
  if (!(node instanceof HTMLElement)) throw new Error(`Missing preview element: ${id}`);
  return node;
}
/** @param {string} id @param {string} text @returns {void} */
function setText(id, text) { element(id).textContent = text; }

/** @returns {void} */
function renderPlayback() {
  const playing = playbackTimer !== null;
  const terminal = step === scenarios[scenario].length - 1;
  element('play-demo').setAttribute('aria-pressed', String(playing));
  setText('playback-label', playing ? 'Pause demo' : terminal ? 'Replay demo' : 'Play demo');
  document.getElementById('playback-icon')?.setAttribute('href', playing ? '#pause' : '#play');
}

/** @returns {void} */
function pausePlayback() {
  if (playbackTimer !== null) window.clearInterval(playbackTimer);
  playbackTimer = null;
  renderPlayback();
}

/** @returns {void} */
function togglePlayback() {
  if (playbackTimer !== null) { pausePlayback(); return; }
  if (step === scenarios[scenario].length - 1) step = 0;
  playbackTimer = window.setInterval(() => {
    step += 1;
    if (step === scenarios[scenario].length - 1) pausePlayback();
    render();
  }, stepDurationMs);
  render();
}

/** @returns {void} */
function createStages() {
  const buttons = scenarios[scenario].map((stage, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'stage';
    button.setAttribute('aria-label', `Stage ${index + 1}: ${stage.label}`);
    const number = document.createElement('span');
    number.className = 'stage-number';
    number.setAttribute('aria-hidden', 'true');
    const title = document.createElement('span');
    title.className = 'stage-title';
    title.textContent = stage.label;
    button.append(number, title);
    button.addEventListener('click', () => { pausePlayback(); step = index; render(); });
    return button;
  });
  element('lifecycle').replaceChildren(...buttons);
}

/** @returns {void} */
function renderChecks() {
  const passed = scenario === 'success' && step >= 3;
  const deadlineMissed = scenario === 'refund' && step >= 2;
  const checking = scenario === 'success' && step === 2;
  element('checks-list').querySelectorAll('li').forEach((row, index) => {
    const result = row.lastElementChild;
    if (!(result instanceof HTMLElement)) return;
    result.textContent = passed ? '✓ Passed' : deadlineMissed ? (index === 2 ? 'Missed' : 'No delivery') : checking ? 'Checking' : 'Pending';
    result.className = passed ? 'passed' : deadlineMissed ? 'waiting' : '';
  });
  setText('checks-note', passed ? 'All three independent checks passed. Policy: all.' : deadlineMissed
    ? 'No delivery to evaluate. The deadline triggers a full refund.'
    : 'Evaluators check the work, not the buyer or seller.');
}

/** @returns {void} */
function render() {
  const stages = scenarios[scenario];
  const current = stages[step];
  const terminal = step === stages.length - 1;
  setText('deal-state', current.state);
  element('deal-state').classList.toggle('refund', scenario === 'refund' && step >= 2);
  setText('held-amount', money(current.held));
  setText('held-note', step === 0 ? 'Awaiting buyer funding' : terminal ? 'No funds remaining in escrow' : 'Reserved for this deal');
  const refundDue = scenario === 'refund' && step >= 2;
  setText('payout-label', refundDue ? (terminal ? 'Buyer refunded' : 'Buyer will receive') : terminal ? 'Seller received' : 'Seller will receive');
  setText('payout-amount', money(refundDue ? priceMinor : priceMinor - feeMinor));
  setText('payout-note', refundDue ? 'Full amount · no fee charged' : 'After a 1% operator fee');
  setText('activity-title', current.title);
  setText('activity-description', current.description);
  setText('event-name', current.event);
  const next = element('next-step');
  if (next.firstChild) next.firstChild.textContent = terminal ? 'Replay deal ' : 'Next step ';
  element('receipt-button').hidden = !terminal;
  element('lifecycle').querySelectorAll('button').forEach((button, index) => {
    button.setAttribute('aria-pressed', String(index === step));
    button.classList.toggle('is-complete', index < step);
    const number = button.querySelector('.stage-number');
    if (number) number.textContent = index < step ? '✓' : String(index + 1).padStart(2, '0');
  });
  renderChecks();
  renderPlayback();
  setText('demo-announcement', `${scenario === 'success' ? 'Approved delivery' : 'Missed deadline'}: ${current.label}. ${current.title}`);
}

/** @returns {{illustrative: true, signed: false, real_money: false, deal_id: string, state: string, currency: string, price_minor: number, held_minor: number, seller_minor: number, fee_minor: number, buyer_refund_minor: number}} */
function sampleReceipt() {
  const settled = scenario === 'success';
  return {
    illustrative: true, signed: false, real_money: false, deal_id: 'D-0042',
    state: settled ? 'SETTLED' : 'REFUNDED', currency: 'EUR',
    price_minor: priceMinor, held_minor: 0,
    seller_minor: settled ? priceMinor - feeMinor : 0,
    fee_minor: settled ? feeMinor : 0, buyer_refund_minor: settled ? 0 : priceMinor,
  };
}

const dialogNode = element('receipt-dialog');
if (!(dialogNode instanceof HTMLDialogElement)) throw new Error('Receipt dialog is unavailable.');
const receiptDialog = dialogNode;

/** @returns {void} */
function openReceipt() {
  if (step !== scenarios[scenario].length - 1) return;
  const receipt = sampleReceipt();
  const rows = [
    ['Deal', receipt.deal_id], ['Outcome', receipt.state],
    ['Original funding', money(receipt.price_minor)], ['Seller payout', money(receipt.seller_minor)],
    ['Operator fee', money(receipt.fee_minor)], ['Buyer refund', money(receipt.buyer_refund_minor)],
    ['Remaining in escrow', money(receipt.held_minor)],
  ];
  element('receipt-details').replaceChildren(...rows.map(([label, value]) => {
    const row = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = label;
    description.textContent = value;
    row.append(term, description);
    return row;
  }));
  setText('download-status', '');
  receiptDialog.showModal();
}

/** @returns {void} */
function downloadReceipt() {
  if (step !== scenarios[scenario].length - 1) return;
  try {
    const blob = new Blob([`${JSON.stringify(sampleReceipt(), null, 2)}\n`], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `cogit-sample-${scenario}-receipt.json`;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setText('download-status', 'Receipt JSON ready to download.');
  } catch {
    setText('download-status', 'Your browser could not prepare the download. The receipt details remain visible above.');
  }
}

document.querySelectorAll('[data-scenario]').forEach((button) => {
  button.addEventListener('click', () => {
    const value = button.getAttribute('data-scenario');
    if (value !== 'success' && value !== 'refund') return;
    pausePlayback();
    scenario = value;
    step = 0;
    document.querySelectorAll('[data-scenario]').forEach((item) => {
      item.setAttribute('aria-pressed', String(item.getAttribute('data-scenario') === scenario));
    });
    createStages();
    render();
  });
});
element('play-demo').addEventListener('click', togglePlayback);
element('next-step').addEventListener('click', () => { pausePlayback(); step = (step + 1) % scenarios[scenario].length; render(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) pausePlayback(); });
window.addEventListener('pagehide', pausePlayback);
element('receipt-button').addEventListener('click', openReceipt);
element('close-receipt').addEventListener('click', () => receiptDialog.close());
element('download-receipt').addEventListener('click', downloadReceipt);
receiptDialog.addEventListener('click', (event) => {
  const box = receiptDialog.getBoundingClientRect();
  if (event.target === receiptDialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) receiptDialog.close();
});

const menuToggle = document.querySelector('.menu-toggle');
/** @param {boolean} open @returns {void} */
function setMenu(open) {
  menuToggle?.setAttribute('aria-expanded', String(open));
  element('site-nav').classList.toggle('is-open', open);
}
menuToggle?.addEventListener('click', () => setMenu(menuToggle.getAttribute('aria-expanded') !== 'true'));
element('site-nav').querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && menuToggle?.getAttribute('aria-expanded') === 'true') {
    setMenu(false);
    if (menuToggle instanceof HTMLElement) menuToggle.focus();
  }
});
createStages();
render();
