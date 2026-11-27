'use strict';
// Original complete character drawings. Each key contains its own continuous
// contours, overlaps, facial expression and contact landmarks. No limb sprites.
const AD = Object.freeze({ paper:'#faf5e9', ink:'#263d38', coral:'#df816a', coralLight:'#f4b59c', blue:'#80a8bd', blueDark:'#52788c', green:'#a8c3a0', forest:'#315d48', yellow:'#edbf56', skin:'#f2c7a3', skinBob:'#bd8662', hair:'#4a3935', muted:'#78847a', white:'#fffdf6' });
const AD_PRESSURE = [[0,.55],[.15,.95],[.5,1],[.83,.85],[1,.5]];
const AD_POSES = {
  rest:{lean:0,head:[0,0],hand:[115,-177],elbow:[98,-230],far:[-98,-183],face:'soft'},
  think:{lean:-6,head:[-7,7],hand:[57,-352],elbow:[132,-257],far:[-99,-174],face:'wonder'},
  prepare:{lean:-12,head:[-12,7],hand:[66,-240],elbow:[93,-220],far:[-100,-177],face:'soft'},
  offer:{lean:12,head:[15,5],hand:[185,-270],elbow:[132,-252],far:[-91,-174],face:'smile'},
  release:{lean:17,head:[20,5],hand:[204,-283],elbow:[143,-270],far:[-89,-174],face:'smile'},
  receive:{lean:8,head:[10,2],hand:[180,-267],elbow:[129,-240],far:[-91,-179],face:'smile'},
  proud:{lean:-2,head:[-3,-7],hand:[131,-300],elbow:[110,-251],far:[-104,-197],face:'smile'},
  workA:{lean:14,head:[20,20],hand:[157,-229],elbow:[131,-242],far:[72,-235],face:'focus'},
  workB:{lean:11,head:[17,16],hand:[155,-246],elbow:[130,-260],far:[72,-235],face:'focus'},
  happy:{lean:-5,head:[-8,-12],hand:[149,-360],elbow:[130,-290],far:[-149,-320],face:'joy'},
};
function adWholePerson(who, pose, blink=false) {
  const q=typeof pose==='string'?AD_POSES[pose]:pose;
  const isAlice=who==='alice', skin=isAlice?AD.skin:AD.skinBob, shirt=isAlice?AD.coral:AD.blue;
  const strokes=[],fills=[];
  const mark=(id,points,width=3.4,color=AD.ink,opacity=1,close=false)=>strokes.push({id,points,width,color,opacity,close,pressure:AD_PRESSURE,corner:1.35});
  const shape=(id,points,fill,width=4.8)=>{fills.push({id,points,color:fill});mark(id,points,width,AD.ink,1,true);};
  // Separate continuous trouser contours; fixed feet shared by every standing pose.
  shape('far-trouser',[[-61,-145],[-10,-143],[-17,-71],[-31,-12],[-64,-12],[-65,-77]],isAlice?'#535d54':'#626c71');
  shape('near-trouser',[[0,-146],[65,-146],[70,-79],[53,-12],[17,-12],[14,-75]],isAlice?'#626e5f':'#767e7d');
  shape('far-shoe',[[-68,-21],[-30,-19],[-22,-8],[-7,-5],[-7,6],[-70,6],[-74,-1]],AD.white,4.5);
  shape('near-shoe',[[17,-21],[53,-20],[69,-8],[87,-5],[90,5],[14,5],[11,-3]],AD.white,4.5);
  mark('far-sole',[[-70,4],[-40,5],[-9,4]],2.6);mark('near-sole',[[17,3],[51,4],[87,3]],2.6);
  mark('near-laces',[[45,-14],[36,-7],[52,-10],[47,-4]],2.2);
  const L=q.lean;
  // Broad continuous sleeves bend as a drawn shape, not hinged rigid capsules.
  function arm(id,side,elbow,wrist,front) {
    const shoulder=[side*57+L,-285];
    const e=elbow,w=wrist;
    const normal=(a,b,r)=>{const d=Math.hypot(b[0]-a[0],b[1]-a[1]);return [-(b[1]-a[1])*r/d,(b[0]-a[0])*r/d];};
    const n=normal(shoulder,e,25),m=normal(e,w,18);
    shape(id+'/sleeve',[[shoulder[0]+n[0],shoulder[1]+n[1]],[e[0]+n[0]*.8,e[1]+n[1]*.8],[w[0]+m[0],w[1]+m[1]],[w[0]-m[0],w[1]-m[1]],[e[0]-n[0]*.8,e[1]-n[1]*.8],[shoulder[0]-n[0],shoulder[1]-n[1]]],front?shirt:(isAlice?'#ca705b':'#6a93a8'),4.7);
    mark(id+'/cuff',[[w[0]+m[0],w[1]+m[1]],[w[0],w[1]+1],[w[0]-m[0],w[1]-m[1]]],3);
    const x=w[0],y=w[1];
    shape(id+'/hand',[[x-11,y-5],[x-5,y-17],[x+4,y-18],[x+13,y-11],[x+21,y-13],[x+26,y-7],[x+20,y+4],[x+7,y+13],[x-8,y+10]],skin,3.7);
    mark(id+'/thumb',[[x+2,y+3],[x+10,y-5],[x+16,y-5]],2.1);
  }
  const far=q.far;
  arm('far-arm',-1,far[0]>0?[L-34,-223]:[-111+L,-243],far,false);
  shape('sweater',[[-34+L,-315],[-70+L,-287],[-79+L*.8,-227],[-67,-144],[-17,-131],[64,-141],[73+L*.7,-218],[62+L,-289],[31+L,-315]],shirt,5.3);
  shape('neck',[[-20+L,-344],[27+L,-344],[27+L,-306],[12+L,-291],[-15+L,-302]],skin,3.5);
  mark('neckline',[[-33+L,-307],[-10+L,-290],[11+L,-286],[33+L,-303]],4);
  mark('hem',[[-62,-151],[-12,-142],[58,-149]],3.2,AD.ink,.7);
  mark('shirt-fold',[[-53+L*.7,-246],[-48+L*.7,-221],[-53+L*.7,-201]],2.1,AD.ink,.5);
  if(!isAlice) {mark('collar-left',[[-33+L,-307],[-14+L,-274],[4+L,-295]],3);mark('collar-right',[[31+L,-306],[24+L,-277],[5+L,-295]],3);}
  arm('near-arm',1,q.elbow,q.hand,true);
  const [hx,hy]=q.head;
  const hp=pts=>pts.map(([x,y])=>[x+hx,y+hy]);
  if(isAlice) {
    shape('hair-back',hp([[-69,-382],[-86,-437],[-61,-482],[-15,-495],[42,-484],[70,-446],[74,-391],[52,-337],[-54,-334]]),AD.hair,5);
    shape('bun',hp([[-69,-449],[-113,-447],[-129,-475],[-111,-500],[-84,-506],[-58,-481]]),AD.hair,4.7);
    mark('bun-ribbon',hp([[-87,-451],[-70,-464],[-59,-478]]),7,AD.coralLight);
  } else {
    shape('hair-back',hp([[-68,-393],[-79,-440],[-54,-476],[-7,-487],[52,-466],[72,-416],[52,-363]]),'#46392e',5);
  }
  shape('face',hp([[-50,-437],[-10,-461],[39,-449],[59,-419],[61,-392],[73,-382],[59,-371],[50,-340],[18,-325],[-14,-332],[-42,-353],[-57,-392]]),skin,4.8);
  shape('ear',hp([[-50,-403],[-69,-408],[-75,-395],[-65,-378],[-49,-378]]),skin,3.6);
  mark('ear-line',hp([[-65,-395],[-57,-398],[-57,-387]]),2.2);
  if(isAlice) {
    shape('fringe',hp([[-57,-391],[-71,-423],[-57,-462],[-21,-481],[22,-478],[51,-452],[48,-432],[19,-440],[-4,-457],[-19,-438],[-32,-428],[-39,-394]]),AD.hair,4.6);
    mark('hair-gloss',hp([[-48,-456],[-31,-467],[-16,-468]]),3,'#8d6c57',.8);
    shape('earring',hp([[-61,-377],[-68,-370],[-63,-361],[-55,-364],[-54,-372]]),AD.yellow,2.6);
  } else {
    shape('quiff',hp([[-60,-412],[-78,-445],[-68,-469],[-49,-467],[-57,-484],[-31,-493],[-6,-478],[9,-498],[30,-486],[35,-465],[58,-467],[69,-448],[51,-427],[30,-433],[9,-453],[-12,-442],[-31,-440],[-37,-411]]),'#46392e',4.9);
    mark('quiff-light',hp([[-42,-472],[-20,-465],[-5,-467]]),3,'#96735b',.9);
  }
  const eyebrow=q.face==='wonder'?-8:q.face==='joy'?-5:0;
  mark('far-brow',hp([[-20,-416+eyebrow],[-8,-422+eyebrow],[0,-418+eyebrow]]),3.2);
  mark('near-brow',hp([[22,-419+eyebrow],[34,-422+eyebrow],[45,-416+eyebrow]]),3.3);
  if(blink||q.face==='joy') {
    mark('eye-far',hp([[-18,-401],[-9,-405],[0,-401]]),3.5);
    mark('eye-near',hp([[24,-401],[34,-405],[43,-401]]),3.5);
  } else {
    mark('eye-far',hp([[-8,-405],[-8,-397]]),5.5);
    mark('eye-near',hp([[35,-406],[35,-397]]),5.8);
  }
  mark('nose',hp([[21,-399],[18,-383],[28,-382]]),2.8);
  if(q.face==='wonder') mark('mouth',hp([[12,-357],[19,-362],[27,-358],[25,-351],[17,-351],[12,-357]]),2.8,AD.ink,1,true);
  else if(q.face==='focus') mark('mouth',hp([[9,-355],[22,-357],[33,-355]]),2.8);
  else mark('mouth',hp([[7,-360],[18,-352],[31,-354],[39,-363]]),3.2);
  mark('cheek',hp([[41,-375],[49,-374]]),6,isAlice?'#df927a':'#9c674f',.55);
  if(!isAlice) {
    mark('glasses-left',hp([[-30,-413],[-7,-416],[9,-411],[7,-389],[-18,-385],[-30,-394]]),3.1,AD.ink,1,true);
    mark('glasses-right',hp([[19,-414],[44,-414],[57,-407],[53,-388],[30,-387],[19,-394]]),3.1,AD.ink,1,true);
    mark('glasses-bridge',hp([[8,-403],[13,-405],[20,-402]]),2.8);
    mark('stubble',hp([[1,-338],[11,-334],[25,-336],[37,-341]]),3.2,'#72543e',.7);
  }
  return {strokes,fills,hand:[q.hand[0]+8,q.hand[1]-2],feet:[[-50,5],[45,5]]};
}
const AD_DRAWINGS = {}, AD_RAW = {}, AD_SPRITES = new Map();
function adRegister(id,raw) {AD_RAW[id]=raw;AD_DRAWINGS[id]=compileCel(raw,{id});}
for(const who of ['alice','bob']) {
  for(const pose of Object.keys(AD_POSES)) adRegister(who+'/'+pose,adWholePerson(who,pose));
  adRegister(who+'/blink',adWholePerson(who,'rest',true));
  for(const [from,to] of [['rest','think'],['think','prepare'],['rest','prepare'],['prepare','offer'],['offer','release'],['offer','rest'],['release','rest'],['rest','receive'],['receive','proud'],['proud','happy'],['rest','proud'],['rest','workA'],['workA','workB'],['workA','offer']]) {
    // A changed expression is a substitution, never a crossfade/morph of eyes.
    for(const [k,u] of [.2,.5,.8].entries()) {
      const pa=AD_POSES[from],pb=AD_POSES[to];
      const pair=(a,b)=>a.map((v,i)=>lerp(v,b[i],u));
      const q={lean:lerp(pa.lean,pb.lean,u),head:pair(pa.head,pb.head),hand:pair(pa.hand,pb.hand),elbow:pair(pa.elbow,pb.elbow),far:pair(pa.far,pb.far),face:u<.5?pa.face:pb.face};
      adRegister(`${who}/${from}-${to}-${k}`,adWholePerson(who,q));
    }
  }
}
function adPoseAt(who,keys,t) {
  let pose=keys[0][1];
  for(const [at,id] of keys) {if(t+1e-6<at)break;pose=id;}
  return who+'/'+pose;
}
function adTransition(keys,at,from,to) {
  keys.push([at,from],[at+2/24,`${from}-${to}-0`],[at+4/24,`${from}-${to}-1`],[at+6/24,`${from}-${to}-2`],[at+8/24,to]);
}
function adPerson(c,id,x,y,scale=1,flip=false) {
  const cacheKey=S+'/'+id;
  if(!AD_SPRITES.has(cacheKey)) {
    const canvas=document.createElement('canvas');canvas.width=Math.ceil(570*S);canvas.height=Math.ceil(550*S);
    const g=canvas.getContext('2d');g.scale(S,S);g.translate(220,520);
    const raw=AD_RAW[id];
    const fills=new Map(raw.fills.map(fill=>[fill.id,fill]));
    // Paint in authored depth order: nearer fills hide the rear contour too.
    for(const stroke of AD_DRAWINGS[id].strokes) {
      const fill=fills.get(stroke.id);
      if(fill){g.fillStyle=fill.color;g.fill(curvePath(fill.points,true,1.35));}
      drawCel(g,{strokes:[stroke]},{material:'ink',color:AD.ink});
    }
    AD_SPRITES.set(cacheKey,canvas);
  }
  c.save();c.translate(x,y);c.scale(flip?-scale:scale,scale);
  const s=AD_SPRITES.get(cacheKey);c.drawImage(s,-220,-520,s.width/S,s.height/S);c.restore();
}
function adContact(id,x,y,scale=1,flip=false) {
  const [hx,hy]=AD_RAW[id].hand;return [x+hx*scale*(flip?-1:1),y+hy*scale];
}
function adPath(c,d,fill=null,width=5,stroke=AD.ink) {
  const path=new Path2D(d);if(fill){c.fillStyle=fill;c.fill(path);}if(width){c.strokeStyle=stroke;c.lineWidth=width;c.lineCap='round';c.lineJoin='round';c.stroke(path);}
}
function adRound(c,x,y,w,h,r,fill,stroke=AD.ink,lw=4) {
  const p=new Path2D();p.roundRect(x,y,w,h,r);c.fillStyle=fill;c.fill(p);if(lw){c.lineWidth=lw;c.strokeStyle=stroke;c.stroke(p);}
}
function adText(c,text,x,y,size=40,color=AD.ink,weight=700,align='center') {
  c.font=`${weight} ${size}px Manrope, sans-serif`;c.fillStyle=color;c.textAlign=align;c.textBaseline='middle';c.fillText(text,x,y);
}
function adCoin(c,x,y,s=1,rot=0) {
  c.save();c.translate(x,y);c.rotate(rot);c.scale(s,s);
  c.fillStyle='#c18e38';c.beginPath();c.ellipse(7,5,43,48,0,0,Math.PI*2);c.fill();
  c.fillStyle=AD.yellow;c.strokeStyle=AD.ink;c.lineWidth=4.5;c.beginPath();c.ellipse(0,0,43,48,0,0,Math.PI*2);c.fill();c.stroke();
  c.strokeStyle='#f9df91';c.lineWidth=3;c.beginPath();c.ellipse(0,0,33,37,0,0,Math.PI*2);c.stroke();
  adText(c,'€',0,1,49,AD.ink,700);c.restore();
}
function adReport(c,x,y,s=1,rot=0,progress=1) {
  c.save();c.translate(x,y);c.rotate(rot);c.scale(s,s);
  adRound(c,-79,-105,164,218,10,'#e2e2cf',AD.ink,3);
  adPath(c,'M -91 -117 L 34 -117 L 78 -75 L 78 101 Q 78 111 67 111 L -91 111 Q -99 111 -99 101 L -99 -107 Q -99 -117 -91 -117 Z',AD.white,4.5);
  adPath(c,'M 34 -117 L 34 -75 L 78 -75',AD.paper,3.5);
  adText(c,'RESEARCH',-13,-73,15,AD.ink,800);
  adPath(c,'M -71 49 L -71 -26 M -71 49 L 50 49',null,2.5,AD.muted);
  for(let i=0;i<3;i++){const h=[30,53,78][i]*clamp(progress*3-i,0,1);if(h>0)adRound(c,-55+i*32,48-h,22,h,3,[AD.coral,AD.blue,AD.green][i],AD.ink,1.8);}
  adPath(c,'M -67 72 L 41 72 M -67 86 L 15 86',null,3.5,'#b1b6a8');c.restore();
}
function adTick(c,x,y,s=1,p=1,color=AD.forest) {
  c.save();c.translate(x,y);c.scale(s,s);c.strokeStyle=color;c.lineWidth=7;c.lineCap='round';c.lineJoin='round';c.beginPath();c.moveTo(-19,0);
  if(p<.35)c.lineTo(lerp(-19,-5,p/.35),lerp(0,14,p/.35));else{c.lineTo(-5,14);c.lineTo(lerp(-5,25,(p-.35)/.65),lerp(14,-22,(p-.35)/.65));}c.stroke();c.restore();
}
function adLock(c,x,y,s=1,open=0) {
  c.save();c.translate(x,y);c.scale(s,s);
  adPath(c,`M -21 -6 L -21 -28 Q -21 -52 0 -52 Q 21 -52 21 -28 L ${21+open*20} ${-6-open*17}`,null,6,AD.ink);
  adRound(c,-35,-9,70,58,12,AD.yellow,AD.ink,4);
  c.fillStyle=AD.ink;c.beginPath();c.arc(0,13,6,0,Math.PI*2);c.fill();adPath(c,'M 0 14 L 0 27',null,5);c.restore();
}
function adDelta(c,x,y,{scale=1,locked=false,coins=false,open=0,joy=false,hand=0}={}) {
  c.save();c.translate(x,y);c.scale(scale,scale);
  // Feet and feet-to-floor contact never drift during a held pose.
  adPath(c,'M -65 -44 L -70 -8 L -94 -3 Q -103 8 -87 10 L -43 10 L -42 -44',AD.forest,4.5);
  adPath(c,'M 43 -43 L 45 10 L 92 10 Q 106 1 89 -4 L 68 -9 L 66 -43',AD.forest,4.5);
  adPath(c,`M -107 -201 Q -151 ${-183-hand*27} -170 ${-208-hand*46}`,null,11,AD.forest);
  adPath(c,`M 111 -201 Q 154 ${-183-hand*27} 173 ${-208-hand*46}`,null,11,AD.forest);
  for(const side of [-1,1]) {c.fillStyle=AD.green;c.strokeStyle=AD.ink;c.lineWidth=4;c.beginPath();c.ellipse(side*173,-208-hand*46,17,19,side*.3,0,Math.PI*2);c.fill();c.stroke();}
  adPath(c,'M -102 -318 Q -120 -315 -120 -291 L -120 -72 Q -117 -41 -85 -38 L 85 -38 Q 120 -41 120 -73 L 120 -291 Q 120 -318 93 -321 Z',AD.green,5.5);
  adPath(c,'M 100 -308 L 100 -79 Q 100 -56 83 -55 L -85 -55',null,5,'#7e9e79');
  adPath(c,'M -11 -295 L 0 -313 L 12 -295 Z',AD.forest,0);
  if(joy)adPath(c,'M -58 -260 Q -45 -278 -32 -260 M 32 -260 Q 45 -278 58 -260',null,5);
  else for(const ex of [-43,43]){c.fillStyle=AD.ink;c.beginPath();c.ellipse(ex,-262,6,9,0,0,Math.PI*2);c.fill();}
  adPath(c,'M -13 -239 Q 0 -227 14 -239',null,4.3);
  adRound(c,-85,-205,170,127,18,'#e6edd4',AD.ink,4);
  if(coins){adCoin(c,-33,-142,.46,-.15);adCoin(c,31,-140,.48,.12);adCoin(c,0,-124,.49,0);}
  if(locked)adLock(c,0,-132,.82,open);
  else if(!coins){adPath(c,'M -35 -141 L 35 -141',null,5,'#aab99f');}
  c.restore();
}
function adSpark(c,x,y,s=1,color=AD.yellow) {
  c.save();c.translate(x,y);c.scale(s,s);adPath(c,'M 0 -17 Q 4 -3 17 0 Q 3 4 0 17 Q -4 3 -17 0 Q -4 -4 0 -17 Z',color,0);c.restore();
}
window.AD_ART={poses:AD_POSES,raw:AD_RAW,contact:adContact};
