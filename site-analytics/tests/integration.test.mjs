import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import net from 'node:net';
import { spawn } from 'node:child_process';

async function availablePort(){return new Promise((resolve,reject)=>{const s=net.createServer();s.on('error',reject);s.listen(0,'127.0.0.1',()=>{const port=s.address().port;s.close(()=>resolve(port));});});}
const password='long-and-complex-test-password';
const secret='test-secret-64-characters-no-real-credentials-xxxxxxxxxxxxxxxxxxxxxx';
async function request(base,url,{method='GET',body,origin,cookie}={}){const headers={};if(origin)headers.Origin=origin;if(cookie)headers.Cookie=cookie;if(body!==undefined)headers['Content-Type']='application/json';const r=await fetch(base+url,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json().catch(()=>({}));return{status:r.status,headers:r.headers,data};}

test('standalone multi-site analytics: authentication, isolation, visitor time and deduplication',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sites-analytics-'));
 const port=await availablePort();const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.execPath,['server.mjs'],{cwd:path.resolve(import.meta.dirname,'..'),env:{...process.env,HOST:'127.0.0.1',PORT:String(port),ADMIN_PASSWORD:password,SESSION_SECRET:secret,DB_PATH:path.join(dir,'test.sqlite'),TRUST_PROXY_HTTPS:'0'},stdio:['ignore','pipe','pipe']});
 let err='';child.stderr.on('data',d=>err+=d.toString());
 t.after(()=>{child.kill();fs.rmSync(dir,{recursive:true,force:true});});
 let ready=false;for(let i=0;i<80;i++){await new Promise(r=>setTimeout(r,60));try{const r=await fetch(base+'/healthz');if(r.ok){ready=true;break;}}catch{}}
 assert.ok(ready,'Server did not start: '+err);
 const html=await fetch(base+'/admin');assert.equal(html.status,200);assert.match(await html.text(),/Мои сайты/);
 assert.equal((await request(base,'/api/admin/summary')).status,401);
 assert.equal((await request(base,'/api/admin/login',{method:'POST',body:{password:'bad'}})).status,401);
 const login=await request(base,'/api/admin/login',{method:'POST',body:{password}});assert.equal(login.status,200);
 const cookie=login.headers.get('set-cookie').split(';')[0];assert.ok(cookie.startsWith('msa_admin='));
 const list=await request(base,'/api/admin/sites',{cookie});assert.deepEqual(list.data.sites.map(s=>s.id),['baking','plants']);
 const bakeUpdate=await request(base,'/api/admin/sites',{cookie,method:'PUT',body:{id:'baking',title:'Здоровая выпечка',origins:['http://localhost:5005']}});assert.equal(bakeUpdate.status,200);
 const plantUpdate=await request(base,'/api/admin/sites',{cookie,method:'PUT',body:{id:'plants',title:'Комнатные растения',origins:['http://localhost:5006']}});assert.equal(plantUpdate.status,200);
 const v=crypto.randomUUID(),sid=crypto.randomUUID(),eid=crypto.randomUUID();
 const event={eventId:eid,visitorId:v,sessionId:sid,kind:'view',page:'/recepty/keks',referrer:'google.com',seconds:0};
 assert.equal((await request(base,'/api/collect?site=baking',{method:'POST',origin:'http://localhost:5006',body:event})).status,403,'Site A must reject origins of B');
 assert.equal((await request(base,'/api/collect?site=baking',{method:'POST',origin:'http://localhost:5005',body:event})).status,202);
 assert.equal((await request(base,'/api/collect?site=baking',{method:'POST',origin:'http://localhost:5005',body:event})).status,202,'Duplicate event must be safe');
 assert.equal((await request(base,'/api/collect?site=baking',{method:'POST',origin:'http://localhost:5005',body:{...event,eventId:crypto.randomUUID(),kind:'heartbeat',seconds:25}})).status,202);
 assert.equal((await request(base,'/api/collect?site=baking',{method:'POST',origin:'http://localhost:5005',body:{...event,eventId:crypto.randomUUID(),kind:'heartbeat',seconds:31}})).status,400);
 assert.equal((await request(base,'/api/collect?site=plants',{method:'POST',origin:'http://localhost:5006',body:{...event,eventId:crypto.randomUUID(),page:'/monstera',seconds:0}})).status,202);
 const bake=await request(base,'/api/admin/details?days=7&site=baking',{cookie});assert.equal(bake.status,200);assert.equal(bake.data.visitors,1);assert.equal(bake.data.visits,1);assert.equal(bake.data.pageviews,1);assert.equal(bake.data.avgSeconds,25);assert.equal(bake.data.pages[0].page,'/recepty/keks');
 const plants=await request(base,'/api/admin/details?days=7&site=plants',{cookie});assert.equal(plants.status,200);assert.equal(plants.data.visitors,1);assert.equal(plants.data.avgSeconds,0);assert.equal(plants.data.pages[0].page,'/monstera');
 const summary=await request(base,'/api/admin/summary?days=7',{cookie});assert.equal(summary.data.totals.visitorsAcrossSites,2);assert.equal(summary.data.totals.pageviews,2);
 const rejectOrigin=await request(base,'/api/admin/sites',{method:'POST',origin:'https://attacker.test',cookie,body:{id:'hacked',title:'Hacked',origins:[]}});assert.equal(rejectOrigin.status,403);
 const rejectHttp=await request(base,'/api/admin/sites',{method:'POST',cookie,body:{id:'hacked',title:'Hacked',origins:['http://example.com']}});assert.equal(rejectHttp.status,400,'Invalid domain is a client error');
 const add=await request(base,'/api/admin/sites',{method:'POST',cookie,body:{id:'new-site',title:'Новый сайт',origins:['https://example.org']}});assert.equal(add.status,201);
 assert.equal((await request(base,'/api/admin/details?site=new-site',{cookie})).data.visitors,0);
});
