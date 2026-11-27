// Playback controls for the same deterministic canvas renderer used by Vidder.
(() => {
  'use strict';
  const renderer = window.CommerceFlowRenderer;
  const flow = window.COMMERCE_FLOW;
  const player = document.getElementById('flow-player');
  const canvas = document.getElementById('flow-canvas');
  if (!renderer || !flow || !player || !canvas) return;
  const context = canvas.getContext('2d');
  if (!context) return;
  const play = document.getElementById('flow-play');
  const replay = document.getElementById('flow-replay');
  const position = document.getElementById('flow-position');
  const time = document.getElementById('flow-time');
  const expand = document.getElementById('flow-expand');
  const status = document.getElementById('flow-status');
  const phaseLabel = document.getElementById('flow-phase');
  const eventLabel = document.getElementById('flow-event');
  const description = document.getElementById('flow-description');
  const route = document.getElementById('flow-route');
  const type = document.getElementById('flow-type');
  const payload = document.getElementById('flow-payload');
  const chapterNav = document.getElementById('flow-chapters');
  const maxFrame = Math.round(renderer.duration * renderer.fps) - 1;
  position.max = String(maxFrame);
  const chapters = flow.phases.map((phase) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = phase.label;
    button.addEventListener('click', () => {
      pause();
      draw(Math.round(phase.offset * renderer.fps));
    });
    chapterNav.append(button);
    return button;
  });
  let frame = 0;
  let playing = false;
  let ready = false;
  let animation = 0;
  let started = 0;
  let previousDetail = '';
  const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  const agentName = (id) => flow.nodes.find((node) => node.id === id)?.name || ({ 'seller-account': 'Seller bank account', 'fee-account': 'Operator fee account' })[id] || id;

  function draw(next) {
    frame = Math.max(0, Math.min(maxFrame, Math.floor(next)));
    context.setTransform(canvas.width / renderer.width, 0, 0, canvas.height / renderer.height, 0, 0);
    renderer.renderFrame(context, frame);
    position.value = String(frame);
    const seconds = frame / renderer.fps;
    time.textContent = `${clock(seconds)} / ${clock(renderer.duration)}`;
    position.setAttribute('aria-valuetext', `${clock(seconds)} of ${clock(renderer.duration)}`);
    player.dataset.frame = String(frame);
    const phaseIndex = Math.max(0, flow.phases.findLastIndex((phase) => seconds >= phase.offset));
    const phase = flow.phases[phaseIndex];
    const event = phase.events.findLast((item) => seconds - phase.offset >= item.at);
    const detailKey = `${phaseIndex}:${event?.at ?? -1}`;
    if (detailKey !== previousDetail) {
      previousDetail = detailKey;
      phaseLabel.textContent = phase.label.toUpperCase();
      eventLabel.textContent = event?.label || phase.title;
      description.textContent = event?.note || phase.subtitle;
      route.textContent = event ? `${agentName(event.from)} → ${(Array.isArray(event.to) ? event.to : [event.to]).map(agentName).join(' + ')}` : phase.subtitle;
      type.textContent = event?.type || 'Protocol overview';
      payload.replaceChildren(...(event?.body || []).map((text) => {
        const item = document.createElement('li');
        item.textContent = text;
        return item;
      }));
      chapters.forEach((button, index) => {
        if (index === phaseIndex) button.setAttribute('aria-current', 'step');
        else button.removeAttribute('aria-current');
      });
    }
  }

  function pause() {
    playing = false;
    cancelAnimationFrame(animation);
    play.textContent = frame === maxFrame ? 'Replay animation' : 'Play animation';
    play.setAttribute('aria-pressed', 'false');
    player.dataset.playing = 'false';
  }

  function tick(now) {
    if (!playing) return;
    draw((now - started) / 1000 * renderer.fps);
    if (frame === maxFrame) {
      pause();
      status.textContent = 'Animation complete. The deal is settled.';
    } else animation = requestAnimationFrame(tick);
  }

  function start() {
    if (!ready) return;
    if (frame === maxFrame) draw(0);
    started = performance.now() - frame / renderer.fps * 1000;
    playing = true;
    player.dataset.playing = 'true';
    play.textContent = 'Pause animation';
    play.setAttribute('aria-pressed', 'true');
    status.textContent = '';
    animation = requestAnimationFrame(tick);
  }

  play.addEventListener('click', () => playing ? pause() : start());
  replay.addEventListener('click', () => { pause(); draw(0); start(); });
  position.addEventListener('input', () => { pause(); draw(Number(position.value)); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => !entry.isIntersecting) && document.fullscreenElement !== player) pause();
  });
  observer.observe(player);
  window.addEventListener('pagehide', () => { pause(); observer.disconnect(); });
  window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (event) => {
    if (event.matches) pause();
  });
  expand.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement === player) await document.exitFullscreen();
      else if (player.requestFullscreen) await player.requestFullscreen();
      else status.textContent = 'Fullscreen is unavailable. Open Current request details to read each message.';
    } catch {
      status.textContent = 'Fullscreen is unavailable. Open Current request details to read each message.';
    }
  });
  document.addEventListener('fullscreenchange', () => {
    expand.textContent = document.fullscreenElement === player ? 'Exit fullscreen' : 'Expand animation';
  });

  // Always start still, including reduced-motion users; movement requires Play.
  document.fonts.ready.then(() => {
    ready = true;
    play.disabled = replay.disabled = position.disabled = false;
    player.dataset.ready = 'true';
    draw(Math.round(1.5 * renderer.fps));
    pause();
  });
})();
