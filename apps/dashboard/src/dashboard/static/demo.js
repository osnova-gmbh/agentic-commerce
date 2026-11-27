'use strict';

const start = document.getElementById('start');
const scenario = document.getElementById('scenario');
const statusLine = document.getElementById('status');
let submitting = false;
let requestKey = null;
let failureMessage = '';

async function demoJSON(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : body.message || 'Request failed');
    error.status = response.status;
    throw error;
  }
  return body;
}

async function refreshDemo() {
  try {
    const state = await demoJSON('/api/demo/status', { cache: 'no-store' });
    start.disabled = submitting || state.running;
    scenario.disabled = start.disabled;
    statusLine.className = 'demo-status' + (state.error || failureMessage ? ' error' : state.running ? ' running' : '');
    if (state.running) {
      statusLine.textContent = 'Agents at work · ' + (state.state || 'Request sent').toLowerCase().replaceAll('_', ' ') + ' · Follow the deal below.';
    } else if (state.error) {
      statusLine.textContent = 'The purchase stopped: ' + state.error;
    } else if (failureMessage) {
      statusLine.textContent = failureMessage;
    } else if (state.state === 'SETTLED') {
      statusLine.textContent = 'Purchase settled. Start another deal, or explore its delivery and payment record below.';
    } else {
      statusLine.textContent = 'Ready when you are. Each purchase uses €500 of simulated funds.';
    }
  } catch (error) {
    start.disabled = scenario.disabled = true;
    statusLine.className = 'demo-status error';
    statusLine.textContent = 'Cannot reach the demo: ' + error.message;
  }
}

start.addEventListener('click', async () => {
  if (submitting) return;
  submitting = true;
  failureMessage = '';
  start.disabled = scenario.disabled = true;
  statusLine.textContent = 'Starting a new purchase…';
  requestKey ||= crypto.randomUUID();
  try {
    const purchase = await demoJSON('/api/demo/purchases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': requestKey },
      body: JSON.stringify({ scenario: scenario.value }),
    });
    requestKey = null;
    location.hash = encodeURIComponent(purchase.deal_id);
  } catch (error) {
    failureMessage = error.message;
    if (error.status && error.status < 500) requestKey = null;
  } finally {
    submitting = false;
    await refreshDemo();
  }
});

scenario.addEventListener('change', () => { requestKey = null; failureMessage = ''; });
async function pollDemo() { await refreshDemo(); setTimeout(pollDemo, 1000); }
pollDemo();
