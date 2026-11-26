const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code=fs.readFileSync('scripts/player.html','utf8').match(/<script>([\s\S]*)<\/script>/)[1];
async function render(time, evening=true, search='') {
 const nodes={};
 for(const id of ['morning','evening','title','info','warning','audio','links','download','script'])
  nodes[id]={id,hidden:false,setAttribute(k,v){this[k]=v;},pause(){},load(){},removeAttribute(k){delete this[k];}};
 const meta={date_jst:'2026-11-26',generated_at_jst:'2026-11-26T07:30:00+09:00',duration_seconds:390};
 class Clock extends Date {constructor(){super(time);} static now(){return new Date(time).getTime();}}
 vm.runInNewContext(code,{Date:Clock,Intl,URLSearchParams,location:{search},document:{getElementById:id=>nodes[id],querySelectorAll:()=>[nodes.morning,nodes.evening]},fetch:async()=>({ok:true,json:async()=>({morning:meta,evening:evening?meta:null})})});
 await new Promise(resolve=>setImmediate(resolve));
 return nodes;
}
(async()=>{
 let n=await render('2026-11-26T07:59:00Z'); assert.equal(n.morning['aria-pressed'],'true'); assert.match(n.audio.src,/today.mp3/);
 n=await render('2026-11-26T08:00:00Z'); assert.equal(n.evening['aria-pressed'],'true'); assert.match(n.audio.src,/evening.mp3/);
 n=await render('2026-11-26T15:00:00Z'); assert.equal(n.morning['aria-pressed'],'true'); assert.equal(n.warning.hidden,false);
 n=await render('2026-11-26T08:00:00Z',false); assert.equal(n.links.hidden,true); assert.equal(n.audio.src,undefined); n.morning.onclick(); assert.match(n.audio.src,/today.mp3/);
 n=await render('2026-11-26T08:00:00Z',true,'?episode=morning'); assert.equal(n.morning['aria-pressed'],'true');
 console.log('Player: 16:59 / 17:00 / midnight / stale / missing evening / manual selection OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
