import {createServer} from 'node:http';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const root=new URL('./',import.meta.url);
const routes=new Map([
  ['/', ['index.html','text/html; charset=utf-8']],
  ['/video.mp4',['out/commerce-flow-final.mp4','video/mp4']],
  ['/poster.png',['out/commerce-flow-poster.png','image/png']],
  ['/commerce-flow.html',['commerce-flow.html','text/html; charset=utf-8']],
  ['/assets/font.css',['assets/font.css','text/css; charset=utf-8']],
  ['/assets/manrope-latin.woff2',['assets/manrope-latin.woff2','font/woff2']],
  ...['flow-data.js','film.js','engine/core.js'].map(path=>['/'+path,[path,'text/javascript; charset=utf-8']]),
]);
const server=createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
  if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{Allow:'GET, HEAD'});res.end();return;}
  const route=routes.get((req.url||'/').split('?')[0]);
  if(!route){res.writeHead(404);res.end();return;}
  const [path,type]=route,file=fileURLToPath(new URL(path,root));
  try{
    const {size}=await stat(file);let start=0,end=size-1,status=200;
    res.setHeader('Content-Type',type);res.setHeader('Accept-Ranges','bytes');
    if(req.headers.range){
      const match=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
      if(match&&(match[1]||match[2])){
        if(match[1]){start=Number(match[1]);end=match[2]?Math.min(Number(match[2]),end):end;}
        else start=Math.max(0,size-Number(match[2]));
      }
      if(!match||!(match[1]||match[2])||!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start>end||start>=size){
        res.writeHead(416,{'Content-Range':'bytes */'+size});res.end();return;
      }
      status=206;res.setHeader('Content-Range','bytes '+start+'-'+end+'/'+size);
    }
    res.setHeader('Content-Length',end-start+1);res.writeHead(status);
    if(req.method==='HEAD'){res.end();return;}
    const stream=createReadStream(file,{start,end});stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
  }catch{if(!res.headersSent)res.writeHead(404);res.end();}
});
server.listen(Number(process.env.PORT||4175),'127.0.0.1',()=>console.log('Flow film: http://127.0.0.1:'+(process.env.PORT||4175)+'/'));
