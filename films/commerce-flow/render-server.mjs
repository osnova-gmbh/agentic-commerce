import {createServer} from 'node:http';
import {createReadStream} from 'node:fs';
import {mkdir,writeFile,readFile,stat,rename,copyFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {dirname,resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=dirname(fileURLToPath(import.meta.url));
const out=join(root,'out');
const ffmpeg=process.env.FFMPEG||'C:/ai/_experiments/vidder/node_modules/ffmpeg-static/ffmpeg.exe';
const port=Number(process.env.RENDER_PORT||4176);
const FRAME_COUNT=1488,FPS=24,DURATION=62;
await mkdir(out,{recursive:true});
let session=null;
const routes=new Map([
  ['/', ['render.html','text/html; charset=utf-8']],
  ['/render.html',['render.html','text/html; charset=utf-8']],
  ['/commerce-flow.html',['commerce-flow.html','text/html; charset=utf-8']],
  ['/engine/core.js',['engine/core.js','text/javascript; charset=utf-8']],
  ['/assets/font.css',['assets/font.css','text/css; charset=utf-8']],
  ['/flow-data.js',['flow-data.js','text/javascript; charset=utf-8']],
  ['/film.js',['film.js','text/javascript; charset=utf-8']],
  ['/video.mp4',['out/commerce-flow-final.mp4','video/mp4']],
  ['/poster.png',['out/commerce-flow-poster.png','image/png']],
]);
function answer(res,code,body){
  res.writeHead(code,{'Content-Type':'application/json; charset=utf-8'});
  res.end(JSON.stringify(body));
}
async function json(req,limit=16*1024*1024){
  const chunks=[];let length=0;
  for await(const chunk of req){
    length+=chunk.length;
    if(length>limit)throw new Error('Request is too large.');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
function active(req){
  if(!session||req.headers['x-render-session']!==session.id)throw new Error('Unknown render session.');
  if(session.encoding||session.done||session.error)throw new Error('This session is no longer accepting frames.');
  return session;
}
function encode(args){
  return new Promise((resolvePromise,reject)=>{
    const child=spawn(ffmpeg,['-hide_banner','-loglevel','error','-y',...args],{windowsHide:true,stdio:['ignore','ignore','pipe']});
    let stderr='';
    child.stderr.on('data',chunk=>{stderr=(stderr+chunk.toString()).slice(-8192);});
    child.on('error',reject);
    child.on('exit',code=>code===0?resolvePromise():reject(new Error('FFmpeg exited '+code+': '+stderr)));
  });
}
async function publish(source,destination){
  try{await stat(destination);await rename(destination,destination+'.previous-'+Date.now());}catch(error){if(error.code!=='ENOENT')throw error;}
  await rename(source,destination);
}
async function finish(s){
  s.encoding=true;
  const base=join(s.directory,'commerce-flow.mp4');
  const final=join(s.directory,'commerce-flow-final.mp4');
  await encode(['-framerate',String(FPS),'-i',join(s.framesDirectory,'%04d.png'),'-frames:v',String(FRAME_COUNT),
    '-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-movflags','+faststart',base]);
  if(s.audio){
    await encode(['-i',base,'-i',join(s.directory,'commerce-flow-score.wav'),'-map','0:v:0','-map','1:a:0',
      '-af','apad','-t',String(DURATION),'-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',final]);
  }else await copyFile(base,final);
  await encode(['-i',final,'-vf','fps=2,scale=320:-2,tile=6x21','-frames:v','1',join(s.directory,'commerce-flow-contact.jpg')]);
  await copyFile(join(s.framesDirectory,'1100.png'),join(s.directory,'commerce-flow-poster.png'));
  const metadata={
    file:resolve(root,'commerce-flow.html'),renderer:'Vidder Canvas in the local browser',
    fps:FPS,frames:FRAME_COUNT,outputFps:FPS,outputFrames:FRAME_COUNT,duration:DURATION,
    size:{w:1920,h:1080,W:1920,H:1080,S:1},audio:s.audio,
  };
  await writeFile(join(s.directory,'commerce-flow-render.json'),JSON.stringify(metadata,null,2)+'\n');
  for(const name of ['commerce-flow.mp4','commerce-flow-final.mp4','commerce-flow-contact.jpg','commerce-flow-poster.png','commerce-flow-render.json']){
    await publish(join(s.directory,name),join(out,name));
  }
  if(s.audio)await publish(join(s.directory,'commerce-flow-score.wav'),join(out,'commerce-flow-score.wav'));
  await publish(s.framesDirectory,join(out,'commerce-flow-frames'));
  s.done=true;s.encoding=false;
  console.log('Finished: '+join(out,'commerce-flow-final.mp4'));
  return metadata;
}
const server=createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  try{
    const pathname=new URL(req.url,'http://127.0.0.1:'+port).pathname;
    if(req.method==='GET'&&pathname==='/api/status'){
      answer(res,200,session?{received:session.received,total:FRAME_COUNT,encoding:session.encoding,done:session.done,error:session.error}: {received:0,total:FRAME_COUNT,done:false});return;
    }
    if(req.method==='POST'){
      if(req.headers.origin&&req.headers.origin!=='http://127.0.0.1:'+port)throw new Error('Unexpected origin.');
      const body=await json(req);
      if(pathname==='/api/start'){
        if(session&&!session.done&&!session.error)throw new Error('A render is already running.');
        if(body.frames!==FRAME_COUNT||body.fps!==FPS||body.size?.w!==1920||body.size?.h!==1080)throw new Error('Unexpected film format.');
        const id=randomUUID(),directory=join(out,'.browser-render-'+id);
        const framesDirectory=join(directory,'frames');
        await mkdir(framesDirectory,{recursive:true});
        session={id,directory,framesDirectory,received:0,audio:false,encoding:false,done:false,error:null};
        answer(res,200,{session:id});return;
      }
      const s=active(req);
      if(pathname==='/api/frames'){
        if(body.start!==s.received||!Array.isArray(body.frames)||body.frames.length<1||body.frames.length>8||s.received+body.frames.length>FRAME_COUNT)throw new Error('Unexpected frame sequence.');
        for(const encoded of body.frames){
          if(typeof encoded!=='string')throw new Error('Invalid frame.');
          const bytes=Buffer.from(encoded,'base64');
          if(!bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw new Error('Expected a PNG frame.');
          await writeFile(join(s.framesDirectory,String(s.received).padStart(4,'0')+'.png'),bytes);
          s.received++;
        }
        answer(res,200,{received:s.received});return;
      }
      if(pathname==='/api/audio'){
        if(s.received!==FRAME_COUNT||typeof body.wav!=='string')throw new Error('Frames must be complete before audio.');
        const wav=Buffer.from(body.wav,'base64');
        if(wav.toString('ascii',0,4)!=='RIFF'||wav.toString('ascii',8,12)!=='WAVE')throw new Error('Expected WAV audio.');
        await writeFile(join(s.directory,'commerce-flow-score.wav'),wav);s.audio=true;
        answer(res,200,{audio:true});return;
      }
      if(pathname==='/api/finish'){
        if(s.received!==FRAME_COUNT)throw new Error('The render is missing frames.');
        try{answer(res,200,await finish(s));}catch(error){s.error=String(error.message);s.encoding=false;throw error;}
        return;
      }
      if(pathname==='/api/fail'){s.error=String(body.error||'Render aborted').slice(0,1024);answer(res,200,{ok:true});return;}
      answer(res,404,{error:'Unknown render endpoint.'});return;
    }
    if(!['GET','HEAD'].includes(req.method)){answer(res,405,{error:'Method not allowed.'});return;}
    const route=routes.get(pathname);
    if(!route){answer(res,404,{error:'Not found.'});return;}
    const [relative,type]=route,file=join(root,relative),info=await stat(file);
    res.setHeader('Content-Type',type);res.setHeader('Content-Length',info.size);
    if(req.method==='HEAD'){res.end();return;}
    const stream=createReadStream(file);stream.on('error',()=>res.destroy());stream.pipe(res);
  }catch(error){if(!res.headersSent)answer(res,400,{error:String(error.message).slice(0,8192)});else res.destroy();}
});
server.listen(port,'127.0.0.1',()=>console.log('Vidder browser export: http://127.0.0.1:'+port+'/'));
