'use strict';
// Stage coordinates are logical 1920 × 1080; the delivery format is explicit.
const AD_STAGE={alice:340,delta:960,bob:1580,ground:840};
let AD_PAPER=null;
function adBackground(c) {
  if(!AD_PAPER) {
    AD_PAPER=layer();const g=AD_PAPER.getContext('2d');g.scale(S,S);
    g.fillStyle=AD.paper;g.fillRect(0,0,W,H);
    g.fillStyle='#f0efdf';g.beginPath();g.ellipse(CX,610,345,280,0,0,Math.PI*2);g.fill();
    g.strokeStyle='#dedfce';g.lineWidth=3;g.beginPath();g.moveTo(132,855);g.bezierCurveTo(601,847,1337,862,1796,849);g.stroke();
    const random=rng(387);g.fillStyle='#9a947c';g.globalAlpha=.075;
    for(let i=0;i<2800;i++)g.fillRect(random()*W,random()*H,.8+random()*1.2,.8);
    g.globalAlpha=1;
    adPath(g,'M 118 848 Q 123 815 102 799 M 118 836 Q 140 816 142 797 M 119 826 Q 98 821 91 808',null,4,'#a2b69a');
    adPath(g,'M 1809 845 Q 1796 815 1812 790 M 1806 832 Q 1781 817 1784 801',null,4,'#a2b69a');
    AD_PAPER=g.canvas;
  }
  resetT(c);blit(c,AD_PAPER);
  for(const [x,rx] of [[340,108],[960,147],[1580,110]]){c.fillStyle='#263d3813';c.beginPath();c.ellipse(x,850,rx,12,0,0,Math.PI*2);c.fill();}
}
function adHeading(c,words) {adText(c,words,CX,139,58,AD.ink,800);}
function adLabels(c,delta=true) {
  for(const [x,name,role,color] of [[340,'Alice','Buyer',AD.coral],[1580,'Bob','Seller',AD.blue],...(delta?[[960,'Delta','Escrow',AD.forest]]:[])]) {
    adText(c,name,x,920,36,AD.ink,800);adText(c,role,x,965,24,AD.muted,500);
    c.fillStyle=color;c.beginPath();c.arc(x-53,964,5,0,Math.PI*2);c.fill();
  }
}
const AD_PAY_KEYS=[[0,'prepare']];
adTransition(AD_PAY_KEYS,.6,'prepare','offer');adTransition(AD_PAY_KEYS,1.15,'offer','release');adTransition(AD_PAY_KEYS,2,'release','rest');
function adFunding(c,t) {
  adBackground(c);adHeading(c,'Delta holds the money.');adLabels(c);
  const alice=adPoseAt('alice',AD_PAY_KEYS,t),bob=t>=3.2&&t<3.325?'bob/blink':'bob/rest';
  adPerson(c,alice,340,840);adPerson(c,bob,1580,840,1,true);
  adDelta(c,960,840,{coins:t>=2,locked:t>=2.2,joy:t>2.5,hand:t>1.4?.2:0});
  if(t<2) {
    const from=adContact(t<1.48?alice:'alice/release',340,840),u=sm(1.48,2,t);
    for(let j=0;j<3;j++) {
      const p=clamp(u*1.25-j*.12,0,1),x=lerp(from[0]+j*11,960+j*21-21,p),y=lerp(from[1]-32-j*16,695,p)-100*Math.sin(p*Math.PI);
      adCoin(c,x,y,.72,lerp(-.13+j*.1,.2,p));
    }
  }
  if(t>=2.25&&t<3.05) {const p=(t-2.25)/.8;adSpark(c,1085,575,Math.sin(p*Math.PI)*1.5);adSpark(c,828,635,Math.sin(p*Math.PI));}
}
const AD_INTRO_KEYS=[[0,'rest']];
adTransition(AD_INTRO_KEYS,.25,'rest','think');adTransition(AD_INTRO_KEYS,3.5,'think','prepare');
function adThought(c,t) {
  const u=sm(.35,.7,t)*(1-sm(3,3.5,t));if(u<=0)return;
  c.save();c.globalAlpha=u;c.translate(573,312);c.scale(.85+.15*u,.85+.15*u);
  adPath(c,'M -127 -75 Q -150 -129 -91 -137 Q -59 -171 -17 -146 Q 35 -176 71 -138 Q 136 -142 145 -91 Q 178 -53 139 -15 Q 149 40 92 47 Q 51 79 9 55 Q -40 82 -73 47 Q -136 56 -137 13 Q -169 -29 -127 -75 Z',AD.white,3.5);
  adReport(c,5,-43,.65,.05);c.restore();
  c.save();c.globalAlpha=u;for(const [x,y,r] of [[410,375,7],[434,350,12]]){c.fillStyle=AD.white;c.strokeStyle=AD.ink;c.lineWidth=3;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill();c.stroke();}c.restore();
}
function adBulb(c,x,y,p) {
  c.save();c.translate(x,y);c.scale(p,p);
  adPath(c,'M -22 22 Q -50 0 -35 -28 Q -20 -57 11 -45 Q 51 -32 35 4 L 21 24 Z','#f4d787',4);
  adPath(c,'M -20 24 L 21 24 L 18 41 L -15 41 Z',AD.white,4);
  adPath(c,'M -9 43 Q 1 55 11 43 M -4 19 L -4 -6 L -17 -14 M -4 -6 L 12 -17',null,3.5);
  for(const [a,b] of [[[-53,-36],[-65,-44]],[[0,-66],[0,-81]],[[51,-35],[65,-45]]])adPath(c,`M ${a} L ${b}`,null,4,AD.yellow);
  c.restore();
}
function adIntro(c,t) {
  adBackground(c);adHeading(c,'A report. A new supplier.');
  adPerson(c,adPoseAt('alice',AD_INTRO_KEYS,t),340,840);
  adPerson(c,t<1.45?'bob/rest':'bob/proud',1580,840,1,true);
  adThought(c,t);
  if(t>1.45&&t<3.5)adBulb(c,1350,346,sm(1.45,1.8,t)*(1-sm(3,3.5,t)));
  if(t>=2.35){const p=sm(2.35,2.8,t);c.save();c.globalAlpha=p;adDelta(c,960,840,{scale:.82+.18*p,hand:1-p});c.restore();}
  adLabels(c,t>=2.75);
}
function adDesk(c,p=1) {
  c.save();c.globalAlpha=p;c.translate((1-p)*160,0);
  adPath(c,'M 1343 689 L 1325 841 M 1685 689 L 1704 841',null,10,'#9b8263');
  adRound(c,1297,677,448,20,9,'#ddc4a1',AD.ink,4.5);
  adPath(c,'M 1324 640 L 1452 640 L 1489 672 L 1351 672 Z',AD.white,3);
  adPath(c,'M 1361 648 L 1437 648 M 1375 657 L 1450 657',null,2.5,AD.blueDark);
  // A mug and a tiny desk plant give Bob a working environment, not a UI.
  adRound(c,1630,621,37,52,8,AD.yellow,AD.ink,3.5);
  adPath(c,'M 1668 631 Q 1690 628 1688 644 Q 1687 658 1667 654',null,3.5);
  adPath(c,'M 1730 640 L 1724 669 L 1695 669 L 1689 640 Z',AD.coralLight,3.5);
  adPath(c,'M 1711 638 L 1711 598 M 1711 628 Q 1686 630 1688 605 Q 1708 604 1711 620 M 1711 616 Q 1732 616 1733 594 Q 1714 594 1711 611',AD.green,3);
  c.restore();
}
const AD_WORK_KEYS=[[0,'rest']];adTransition(AD_WORK_KEYS,.2,'rest','workA');
for(let j=0;j<5;j++){AD_WORK_KEYS.push([.7+j*.5,'workA'],[.95+j*.5,'workB']);}
AD_WORK_KEYS.push([3.2,'workA']);adTransition(AD_WORK_KEYS,3.55,'workA','offer');
function adWork(c,t) {
  adBackground(c);adHeading(c,'Bob gets to work.');adLabels(c);
  adPerson(c,t>=2.5&&t<2.625?'alice/blink':'alice/rest',340,840);
  adDelta(c,960,840,{coins:true,locked:true});
  const bob=adPoseAt('bob',AD_WORK_KEYS,t);adPerson(c,bob,1580,840,1,true);
  const deskOpacity=sm(0,.45,t)*(1-sm(3.5,4.1,t));adDesk(c,deskOpacity);
  if(t>=.5&&t<3.5) {
    const hand=adContact(bob,1580,840,1,true);c.save();c.globalAlpha=deskOpacity;
    adPath(c,`M ${hand[0]+8} ${hand[1]-23} L ${hand[0]-17} ${hand[1]+41}`,null,10,AD.yellow);
    adPath(c,`M ${hand[0]-17} ${hand[1]+41} L ${hand[0]-22} ${hand[1]+52}`,null,5,AD.ink);c.restore();
  }
  if(t>=.7){
    const p=sm(3.55,4.5,t),grip=adContact('bob/offer',1580,840,1,true);
    c.save();c.globalAlpha=sm(.7,1,t);adReport(c,lerp(1248,grip[0],p),lerp(330,grip[1]-105*.9,p),.9,lerp(-.08,0,p),sm(.9,3.3,t));c.restore();
    if(t>2.85&&t<3.5)adSpark(c,1360,236,Math.sin((t-2.85)/.65*Math.PI)*1.4);
  }
}
function adLens(c,x,y,angle=0) {
  c.save();c.translate(x,y);c.rotate(angle);
  adPath(c,'M 33 34 L 81 84',null,17,AD.yellow);adPath(c,'M 33 34 L 81 84',null,3.4);
  c.fillStyle='#ffffff73';c.strokeStyle=AD.ink;c.lineWidth=5;c.beginPath();c.arc(0,0,48,0,Math.PI*2);c.fill();c.stroke();
  adPath(c,'M -27 -11 Q -18 -32 -2 -31',null,6,AD.white);c.restore();
}
function adCheckBadges(c,t) {
  for(let j=0;j<3;j++){
    const x=837+j*123,y=471,start=1.6+j*.8,p=sm(start,start+.3,t);
    c.fillStyle=p>0?'#d7e4c6':AD.white;c.strokeStyle=p>0?AD.forest:'#b7c3af';c.lineWidth=3;c.beginPath();c.arc(x,y,32,0,Math.PI*2);c.fill();c.stroke();
    if(p>0)adTick(c,x,y,.72,p);
    else {c.fillStyle='#a8b39f';for(const dx of [-10,0,10]){c.beginPath();c.arc(x+dx,y,2.5,0,Math.PI*2);c.fill();}}
  }
}
const AD_SEND_KEYS=[[0,'offer']];adTransition(AD_SEND_KEYS,.25,'offer','release');adTransition(AD_SEND_KEYS,1.1,'release','rest');
function adChecks(c,t) {
  adBackground(c);adHeading(c,'Independent checks.');adLabels(c);
  adPerson(c,t>=3.8&&t<3.925?'alice/blink':'alice/rest',340,840);
  const bob=adPoseAt('bob',AD_SEND_KEYS,t);adPerson(c,bob,1580,840,1,true);
  adDelta(c,960,840,{coins:true,locked:true});
  const moving=sm(.65,1.4,t),grip=adContact(t<.65?bob:'bob/release',1580,840,1,true);
  adReport(c,lerp(grip[0],960,moving),lerp(grip[1]-105*.9,323,moving)-65*Math.sin(moving*Math.PI),.9,Math.sin(moving*Math.PI)*.15);
  if(t>=1.4){
    adCheckBadges(c,t);
    if(t<3.7){const z=sm(1.4,3.7,t);adLens(c,lerp(887,1040,z),302+18*Math.sin(z*Math.PI*2),-.14);}
    else {adSpark(c,1090,284,sm(3.7,4,t)*1.4);adSpark(c,813,326,sm(3.8,4.1,t));}
  }
}
const AD_RECEIVE_ALICE=[[0,'rest']];adTransition(AD_RECEIVE_ALICE,.15,'rest','receive');
const AD_RECEIVE_BOB=[[0,'rest']];adTransition(AD_RECEIVE_BOB,1.9,'rest','receive');adTransition(AD_RECEIVE_BOB,4,'receive','proud');
function adDelivery(c,t) {
  adBackground(c);adHeading(c,'Work delivered. Bob paid.');adLabels(c);
  const alice=adPoseAt('alice',AD_RECEIVE_ALICE,t),bob=adPoseAt('bob',AD_RECEIVE_BOB,t);
  adPerson(c,alice,340,840);adPerson(c,bob,1580,840,1,true);
  adDelta(c,960,840,{coins:t<2.1,locked:t<2.1,open:sm(1.65,2.1,t),joy:t>2.1,hand:t>3.3?.45:0});
  const a=adContact(alice,340,840),p=sm(.35,1.5,t),rx=lerp(960,a[0],p),ry=lerp(323,a[1]-105*.9,p)-70*Math.sin(p*Math.PI);
  adReport(c,rx,ry,.9,-.06*Math.sin(p*Math.PI));
  c.save();c.translate(rx+58,ry+72);c.fillStyle=AD.green;c.strokeStyle=AD.ink;c.lineWidth=2.5;c.beginPath();c.arc(0,0,24,0,Math.PI*2);c.fill();c.stroke();adTick(c,0,0,.5);c.restore();
  if(t>=2.1) {
    const h=adContact(bob,1580,840,1,true),u=sm(2.1,3.4,t);
    for(let j=0;j<3;j++) {const z=clamp(u*1.25-j*.12,0,1);adCoin(c,lerp(960+j*14-14,h[0]+j*10,z),lerp(705,h[1]-28-j*16,z)-130*Math.sin(z*Math.PI),lerp(.48,.72,z),-.13+j*.1);}
  }
  if(t>3.5&&t<4.25){const s=Math.sin((t-3.5)/.75*Math.PI);adSpark(c,1372,451,s*1.4);adSpark(c,576,389,s*1.2);}
}
const AD_END_ALICE=[[0,'receive']];adTransition(AD_END_ALICE,.15,'receive','proud');adTransition(AD_END_ALICE,.8,'proud','happy');
const AD_END_BOB=[[0,'proud']];adTransition(AD_END_BOB,.6,'proud','happy');
function adEnding(c,t) {
  adBackground(c);adHeading(c,'Good work. Fair trade.');adLabels(c);
  const alice=adPoseAt('alice',AD_END_ALICE,t),bob=adPoseAt('bob',AD_END_BOB,t);
  adPerson(c,alice,340,840);adPerson(c,bob,1580,840,1,true);
  adDelta(c,960,840,{joy:true,hand:lerp(.45,1,sm(.4,.9,t))});
  const a=adContact(alice,340,840),b=adContact(bob,1580,840,1,true);
  adReport(c,a[0],a[1]-105*.9,.9);
  c.save();c.fillStyle=AD.green;c.beginPath();c.arc(a[0]+58,a[1]-22,24,0,Math.PI*2);c.fill();adTick(c,a[0]+58,a[1]-22,.5);c.restore();
  for(let j=0;j<3;j++)adCoin(c,b[0]+j*10,b[1]-28-j*16,.72,-.13+j*.1);
  const p=sm(.4,1,t);for(const [x,y,s] of [[694,333,1.3],[1206,382,1],[1005,267,.8],[728,681,.6],[1203,694,.65]])adSpark(c,x,y,s*p);
  if(t>.7){c.save();c.globalAlpha=sm(.7,1.1,t);adTick(c,960,386,1.55);c.restore();}
}
function adScore(ac,t0,destination) {
  const master=ac.createGain();master.gain.setValueAtTime(0,t0);master.gain.linearRampToValueAtTime(2,t0+.35);master.gain.setValueAtTime(2,t0+24.7);master.gain.linearRampToValueAtTime(0,t0+25.9);master.connect(destination);
  const melody=[523.25,659.25,783.99,659.25,587.33,659.25,440,392];
  for(let k=0;k<40;k++){const t=k*.625+.12;note(ac,master,melody[k%8],t0,t,.38,'sine',k%4===0?.12:.075);if(k%2===0)note(ac,master,[130.81,164.81,174.61,196][Math.floor(k/8)%4],t0,t,.78,'triangle',.08);}
  // Musical sound effects are authored at the action frames, not added at random.
  for(const [t,f] of [[2.65,392],[6,880],[6.2,1174.66],[13.65,660],[14.75,784],[15.55,988],[16.35,1175],[19.5,1046.5],[21.3,880],[21.45,1175],[23.9,1318.5]])note(ac,master,f,t0,t,.27,'triangle',.12);
  for(let j=0;j<10;j++)noiseBurst(ac,master,t0,8.8+j*.22,.045,.025,883+j);
  for(const t of [5.5,13.6,18.5])noiseBurst(ac,master,t0,t,.18,.022,417);
}
const AD_TIMELINE=[
  {name:'alice-needs-research',dur:4,fn:adIntro},
  {name:'delta-holds-payment',dur:4,fn:adFunding},
  {name:'bob-makes-the-report',dur:5,fn:adWork},
  {name:'independent-delivery-checks',dur:5,fn:adChecks},
  {name:'report-delivered-payment-released',dur:5,fn:adDelivery},
  {name:'a-fair-deal',dur:3,fn:adEnding},
];
window.AD_FILM={timeline:AD_TIMELINE.map(({name,dur})=>({name,dur})),stage:AD_STAGE};
defineFilm({palette:{...PALETTES.pencilMinimal,paper:AD.paper},format:{ar:'16:9',width:1920},fps:24,timeline:AD_TIMELINE,score:adScore});
