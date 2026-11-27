'use strict';
const purchase = document.getElementById('purchase');
const statusNode = document.getElementById('status');
const connection = document.getElementById('connection');
const reference = document.getElementById('reference');
let requestKey = null;
let submitting = false;
async function read(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The request failed.');
  return body;
}
async function refresh() {
  try {
    const [runtime, current] = await Promise.all([read('/api/runtime'), read('/api/demo/status')]);
    connection.textContent = runtime.ready ? 'AgentDb connected · four workers' : 'Worker unavailable';
    purchase.disabled = submitting || current.running || !runtime.ready || Boolean(runtime.scheduler_error);
    statusNode.classList.toggle('error', Boolean(current.error || runtime.scheduler_error));
    statusNode.textContent = current.error || runtime.scheduler_error || (current.state ? 'Transaction: ' + current.state : current.running ? 'Your purchase is being started…' : 'Ready for a new purchase.');
    reference.textContent = current.deal_id ? 'Deal ' + current.deal_id : '';
    if (!current.running && !submitting) requestKey = null;
  } catch (error) { connection.textContent = 'Connection unavailable'; statusNode.textContent = error.message; purchase.disabled = true; }
}
purchase.addEventListener('click', async () => {
  submitting = true; purchase.disabled = true;
  requestKey ||= crypto.randomUUID();
  try {
    await read('/api/demo/purchases', {method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':requestKey}, body:JSON.stringify({scenario:'happy'})});
    statusNode.textContent = 'Purchase accepted. The workers are handling your transaction.';
  } catch(error) { statusNode.textContent = error.message; }
  finally { submitting = false; await refresh(); }
});
async function poll() { await refresh(); setTimeout(poll, 2000); }
poll();
