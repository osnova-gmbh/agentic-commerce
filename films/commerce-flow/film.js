'use strict';

const CF = {
  paper: '#f4f7f3', ink: '#193c30', muted: '#63776e', line: '#d9e4dc',
  blue: '#3678b0', green: '#2d7c58', purple: '#8263b1', gold: '#a87828',
  panel: '#ffffff', tint: '#edf4ee',
};
const CF_X = [172, 388, 604, 820, 1036, 1252];
const CF_IDX = Object.fromEntries(CF_NODES.map((node, index) => [node.id, index]));
const CF_KIND = {
  query: [CF.purple, 'DIRECT MODULE CALL'],
  message: [CF.blue, 'SIGNED DEAL MESSAGE'],
  reply: [CF.green, 'RESPONSE / CONFIRMATION'],
  money: [CF.gold, 'BANK TRANSFER'],
  artifact: [CF.purple, 'ARTIFACT STORAGE'],
};

function cfBox(c, x, y, width, height, fill, stroke, radius = 12) {
  c.beginPath(); c.roundRect(x, y, width, height, radius);
  if (fill) { c.fillStyle = fill; c.fill(); }
  if (stroke) { c.strokeStyle = stroke; c.lineWidth = 1.5; c.stroke(); }
}

function cfText(c, text, x, y, size = 24, weight = 500, color = CF.ink, align = 'left') {
  c.fillStyle = color; c.font = weight + ' ' + size + 'px Manrope, Arial, sans-serif';
  c.textAlign = align; c.textBaseline = 'alphabetic'; c.fillText(text, x, y);
}

function cfFit(c, text, x, y, width, size = 22, color = CF.ink, align = 'left', weight = 500) {
  c.font = weight + ' ' + size + 'px Manrope, Arial, sans-serif';
  while (c.measureText(text).width > width && size > 15) {
    size -= .5; c.font = weight + ' ' + size + 'px Manrope, Arial, sans-serif';
  }
  cfText(c, text, x, y, size, weight, color, align);
}

function cfWrap(c, text, x, y, width, size = 23, lineHeight = 33, weight = 500, color = CF.ink) {
  c.font = weight + ' ' + size + 'px Manrope, Arial, sans-serif';
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? line + ' ' + word : word;
    if (line && c.measureText(next).width > width) {
      cfText(c, line, x, y, size, weight, color); y += lineHeight; line = word;
    } else line = next;
  }
  if (line) cfText(c, line, x, y, size, weight, color);
  return y + lineHeight;
}

function cfColor(event) { return CF_KIND[event.kind]?.[0] || CF.blue; }
function cfTargets(event) { return Array.isArray(event.to) ? event.to : [event.to]; }
function cfNodeId(id) { return id === 'seller-account' ? 'seller' : id === 'fee-account' ? 'escrow' : id; }
function cfName(id) {
  if (id === 'seller-account') return 'Seller bank account';
  if (id === 'fee-account') return 'Operator fee account';
  return CF_NODES[CF_IDX[id]]?.name || id;
}

function cfHeader(c, phase, index, time) {
  cfText(c, 'cogit / finance', 60, 56, 27, 750);
  cfText(c, 'PROTOCOL WALKTHROUGH · SIMULATED FUNDS', 1858, 54, 18, 650, CF.muted, 'right');
  cfText(c, phase.title, 60, 139, 53, 650);
  cfText(c, phase.subtitle, 62, 187, 24, 450, CF.muted);
  const labels = CF_PHASES.slice(0, -1);
  labels.forEach((item, n) => {
    const x = 62 + n * 259;
    cfBox(c, x, 1041, 231, 4, n < index ? CF.green : n === index ? CF.blue : CF.line, null, 2);
    cfText(c, item.label, x, 1032, 16, n === index ? 750 : 500, n <= index ? CF.ink : '#8b9b93');
  });
}

function cfNodes(c, event) {
  const active = new Set(event ? [event.from, ...cfTargets(event)].map(cfNodeId) : CF_NODES.map(n => n.id));
  CF_NODES.forEach((node, index) => {
    const x = CF_X[index], lit = active.has(node.id);
    cfBox(c, x - 99, 262, 198, 117, lit ? '#f7faf6' : '#fafbf9', lit ? node.color : CF.line, 9);
    c.fillStyle = lit ? node.color : '#a0b1a6'; c.beginPath(); c.arc(x, 282, 4, 0, TAU); c.fill();
    cfFit(c, node.name, x, 320, 174, 22, lit ? CF.ink : CF.muted, 'center', 650);
    cfFit(c, node.detail, x, 349, 174, 16, CF.muted, 'center');
    c.strokeStyle = '#dae5dd'; c.lineWidth = 1; c.setLineDash([5, 8]);
    c.beginPath(); c.moveTo(x, 390); c.lineTo(x, 888); c.stroke(); c.setLineDash([]);
  });
}

function cfPoint(path, progress) {
  const lengths = path.slice(1).map((point, i) => Math.hypot(point[0] - path[i][0], point[1] - path[i][1]));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  let distance = total * progress;
  for (let i = 0; i < lengths.length; i++) {
    if (distance <= lengths[i] || i === lengths.length - 1) {
      const ratio = lengths[i] ? distance / lengths[i] : 0;
      return [lerp(path[i][0], path[i + 1][0], ratio), lerp(path[i][1], path[i + 1][1], ratio), i];
    }
    distance -= lengths[i];
  }
  return [...path.at(-1), lengths.length - 1];
}

function cfPath(c, path, progress, color, width, dashed = false) {
  const [x, y, segment] = cfPoint(path, progress);
  c.strokeStyle = color; c.lineWidth = width; c.lineCap = 'round';
  c.setLineDash(dashed ? [7, 7] : []);
  c.beginPath(); c.moveTo(...path[0]);
  for (let i = 1; i <= segment; i++) c.lineTo(...path[i]);
  c.lineTo(x, y); c.stroke(); c.setLineDash([]);
  return [x, y];
}

function cfRoute(c, event, target, y, progress, current) {
  const source = CF_X[CF_IDX[cfNodeId(event.from)]], destination = CF_X[CF_IDX[cfNodeId(target)]];
  const isAccount = target.endsWith('-account');
  const direction = destination >= source ? 1 : -1;
  const end = isAccount ? destination - direction * 88 : destination;
  const path = event.from === target ? [[source,y],[source+66,y],[source+66,y+19],[source,y+19]] : [[source,y],[end,y]];
  const color = current ? cfColor(event) : '#9aad9f';
  cfPath(c, path, 1, '#e5ede7', 2, event.kind === 'query');
  const point = cfPath(c, path, progress, color, current ? 3 : 2, event.kind === 'query');
  const final = path.at(-1), previous = path.at(-2), angle = Math.atan2(final[1]-previous[1], final[0]-previous[0]);
  if (progress >= .99) {
    c.save(); c.translate(...final); c.rotate(angle); c.fillStyle = color;
    c.beginPath(); c.moveTo(1,0); c.lineTo(-12,-6); c.lineTo(-12,6); c.closePath(); c.fill(); c.restore();
  } else if (progress > 0) {
    cfBox(c, point[0]-8, point[1]-5, 16, 10, cfColor(event), null, 3);
  }
  if (isAccount) {
    cfBox(c, destination-85, y-17, 170, 34, '#fcf5e8', '#e2cea5', 5);
    cfFit(c, target === 'seller-account' ? 'Seller account' : 'Operator account', destination, y+5, 152, 16, CF.gold, 'center', 650);
  }
}

function cfSequence(c, phase, time, activeIndex) {
  cfBox(c, 60, 239, 1316, 677, CF.panel, CF.line);
  const active = activeIndex >= 0 ? phase.events[activeIndex] : null;
  cfNodes(c, active);
  phase.events.forEach((event, index) => {
    if (time < event.at) return;
    const y = 435 + index * (phase.events.length > 5 ? 79 : 93);
    const current = index === activeIndex;
    if (current) cfBox(c, 78, y-36, 1280, event.from === event.to ? 77 : 69, '#eff5f0', null, 7);
    const progress = sm(event.at, event.arrive, time);
    const ids = [event.from, ...cfTargets(event)].map(cfNodeId);
    const min = Math.min(...ids.map(id => CF_X[CF_IDX[id]]));
    const max = Math.max(...ids.map(id => CF_X[CF_IDX[id]]));
    const middle = min === max ? min + 140 : (min+max)/2;
    for (const target of cfTargets(event)) cfRoute(c, event, target, y+9, progress, current);
    const labelWidth = Math.max(175, max-min-28);
    c.font = (current ? 650 : 500) + ' 21px Manrope';
    const measured = Math.min(c.measureText(event.label).width + 18, labelWidth + 18);
    cfBox(c, middle-measured/2, y-25, measured, 30, current ? '#eff5f0' : '#fff', null, 4);
    cfFit(c, event.label, middle, y-3, labelWidth, 21, current ? cfColor(event) : CF.muted, 'center', current ? 650 : 500);
    cfText(c, String(index+1).padStart(2,'0'), 90, y+16, 16, 600, current ? cfColor(event) : '#a4b3a9');
  });
  const legend = [['#3678b0','Deal message'],['#8263b1','Catalog / artifact'],['#a87828','Bank transfer'],['#2d7c58','Confirmation']];
  legend.forEach(([color,label], index) => {
    const x = 91 + index*321; c.fillStyle=color; c.beginPath(); c.arc(x,889,4,0,TAU); c.fill();
    cfText(c,label,x+14,894,14,500,CF.muted);
  });
}

function cfAside(c, phase, event, state) {
  cfBox(c, 1405, 239, 453, 677, '#eaf1eb', '#d5e1d7', 12);
  const color = event ? cfColor(event) : CF.ink;
  cfText(c, event ? CF_KIND[event.kind][1] : 'NEXT IN THE FLOW', 1434, 279, 15, 750, color);
  cfWrap(c, event?.label || phase.label, 1434, 325, 393, 34, 43, 650);
  if (event) {
    const names = cfTargets(event).map(cfName);
    const target = names.length > 1 ? 'Buyer + seller' : names[0];
    cfFit(c, cfName(event.from) + ' → ' + target, 1434, 402, 390, 18, CF.muted);
    cfBox(c, 1428, 422, 405, 54, '#fff', '#d7e3d9', 7);
    cfFit(c, event.type, 1444, 455, 372, 22, color, 'left', 650);
    cfText(c, 'DETAILS', 1434, 510, 14, 750, CF.muted);
    let y = 548;
    for (const body of event.body) {
      y = cfWrap(c, body, 1434, y, 389, 22, 30, 500) + 11;
    }
    cfWrap(c, event.note, 1434, 751, 389, 23, 33, 500);
  } else {
    cfWrap(c, phase.subtitle, 1434, 434, 384, 26, 38, 500);
    cfText(c, 'Follow the arrows.', 1434, 655, 24, 650);
    cfWrap(c, 'Source, destination and message contents stay visible as each request moves.', 1434, 698, 378, 23, 34, 450, CF.muted);
  }
  cfBox(c, 1428, 859, 406, 36, '#fff', null, 5);
  cfText(c, 'DEAL STATE', 1442, 882, 13, 700, CF.muted);
  cfFit(c, state, 1819, 883, 275, 17, CF.ink, 'right', 700);
}

function cfBalances(c, values) {
  const entries = [
    ['BUYER NET CHANGE', values[0] ? '−€500' : '€0'],
    ['HELD IN ESCROW', '€' + values[1]],
    ['SELLER RECEIVED', '€' + values[2]],
    ['OPERATOR FEE', '€' + values[3]],
  ];
  entries.forEach(([label, amount], index) => {
    const x = 60 + index*458;
    cfBox(c, x, 934, 424, 70, index===1 && values[1] ? '#e4efdf' : '#fff', CF.line, 8);
    cfText(c,label,x+18,958,13,700,CF.muted);
    cfText(c,amount,x+403,986,29,650,CF.ink,'right');
  });
}

function cfComplete(c, phase, time, index) {
  const opacity = sm(0, .7, time);
  c.save(); c.globalAlpha = opacity;
  cfBox(c,60,243,1798,674,'#e7f0e5', '#cbdacb', 18);
  c.strokeStyle=CF.green;c.lineWidth=9;c.lineCap='round';c.lineJoin='round';
  c.beginPath();c.moveTo(859,348);c.lineTo(922,413);c.lineTo(1058,288);c.stroke();
  cfText(c,'SETTLED',960,486,30,750,CF.green,'center');
  cfText(c,'The buyer has the delivery.',960,553,40,600,CF.ink,'center');
  cfText(c,'The seller has the payment.',960,610,40,600,CF.ink,'center');
  cfText(c,'Both have a signed receipt.',960,667,40,600,CF.ink,'center');
  cfText(c,'Signed deal messages. Independent checks. Auditable payments.',960,813,25,500,CF.muted,'center');
  c.restore();
}

function cfDraw(phase, index, c, time) {
  c.fillStyle=CF.paper;c.fillRect(0,0,W,H);
  cfHeader(c,phase,index,time);
  let values=[...phase.balances], state=phase.state, activeIndex=-1;
  phase.events.forEach((event,n) => {
    if(time>=event.at)activeIndex=n;
    if(time>=event.arrive) {
      if(event.balances)values=[...event.balances];
      if(event.state)state=event.state;
    }
  });
  if(phase.id==='complete')cfComplete(c,phase,time,index);
  else {
    cfSequence(c,phase,time,activeIndex);
    cfAside(c,phase,activeIndex<0 ? null : phase.events[activeIndex],state);
  }
  cfBalances(c,values);
}

function cfScore(ac,t0,destination) {
  const gain=ac.createGain();gain.gain.value=.45;gain.connect(destination);
  for (const phase of CF_PHASES) for (const event of phase.events) {
    const frequency=event.kind==='money'?392:event.kind==='reply'?784:523.25;
    note(ac,gain,frequency,t0,phase.offset+event.arrive,.15,'sine',.025);
  }
  for (const [n,f] of [523.25,659.25,783.99].entries()) {
    note(ac,gain,f,t0,CF_PHASES.at(-1).offset+n*.16,.65,'sine',.035);
  }
}

Promise.all([document.fonts.load('500 24px Manrope'),document.fonts.load('750 53px Manrope')]).then(() => {
  defineFilm({
    palette:{...PALETTES.pencilMinimal,paper:CF.paper,finish:'flat'},
    format:{ar:'16:9',width:1920},fps:24,
    timeline:CF_PHASES.map((phase,index)=>({name:phase.id,dur:phase.duration,fn:(c,t)=>cfDraw(phase,index,c,t)})),
    score:cfScore,
  });
});
