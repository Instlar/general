import http from 'node:http';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { DatabaseSync } from 'node:sqlite';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const env = process.env;
const host = env.HOST || '127.0.0.1';
const port = Number(env.PORT || 4301);
const dbPath = path.resolve(ROOT, env.DB_PATH || './data/analytics.sqlite');
const password = env.ADMIN_PASSWORD || '';
const sessionSecret = env.SESSION_SECRET || '';
if (password.length < 16 || sessionSecret.length < 32) {
  console.error('Configure ADMIN_PASSWORD (>=16 chars) and SESSION_SECRET (>=32 chars) in environment.');
  process.exit(1);
}
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT');
fs.mkdirSync(path.dirname(dbPath), { recursive: true, mode: 0o700 });
const db = new DatabaseSync(dbPath);
db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sites (
  id TEXT PRIMARY KEY, title TEXT NOT NULL,
  origins TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES sites(id),
  visitor_id TEXT NOT NULL, session_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('view','heartbeat')),
  page TEXT NOT NULL, referrer TEXT NOT NULL DEFAULT '',
  seconds INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ev_site_time ON events(site_id, created_at);
CREATE INDEX IF NOT EXISTS ev_site_kind_time ON events(site_id,kind,created_at);
CREATE INDEX IF NOT EXISTS ev_site_visitor ON events(site_id,visitor_id);
CREATE TABLE IF NOT EXISTS sessions (
  site_id TEXT NOT NULL REFERENCES sites(id), session_id TEXT NOT NULL,
  visitor_id TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  views INTEGER NOT NULL DEFAULT 0, visible_seconds INTEGER NOT NULL DEFAULT 0,
  referrer TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(site_id, session_id)
);
CREATE INDEX IF NOT EXISTS sess_site_start ON sessions(site_id,started_at);
`);
const insertSite = db.prepare('INSERT OR IGNORE INTO sites (id,title) VALUES (?,?)');
insertSite.run('baking','Здоровая выпечка');
insertSite.run('plants','Комнатные растения');
const getSite = db.prepare('SELECT id,title,origins FROM sites WHERE id=?');
const listSites = db.prepare('SELECT id,title,origins FROM sites ORDER BY CASE id WHEN \'baking\' THEN 0 WHEN \'plants\' THEN 1 ELSE 2 END, title');
const insertEvent = db.prepare('INSERT OR IGNORE INTO events(event_id,site_id,visitor_id,session_id,kind,page,referrer,seconds) VALUES(?,?,?,?,?,?,?,?)');
const insertSession = db.prepare(`INSERT INTO sessions(site_id,session_id,visitor_id,views,visible_seconds,referrer)
VALUES(?,?,?,?,?,?) ON CONFLICT(site_id,session_id) DO UPDATE SET
  last_seen_at=datetime('now'),views=sessions.views+excluded.views,
  visible_seconds=sessions.visible_seconds+excluded.visible_seconds`);
const updateSite = db.prepare('UPDATE sites SET title=?,origins=? WHERE id=?');
const createSite = db.prepare('INSERT INTO sites(id,title,origins) VALUES(?,?,?)');

function reply(res,status,data,headers={}) { const payload=JSON.stringify(data);res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...headers});res.end(payload); }
function cleanText(s,max=120) { return String(s ?? '').slice(0,max).replace(/[\x00-\x1f\x7f]/g,''); }
function validId(s) { return typeof s==='string' && /^[a-z0-9-]{2,40}$/.test(s); }
function validUuid(s) { return typeof s==='string' && /^[0-9a-f-]{16,64}$/i.test(s); }
function invalidSite(message){return Object.assign(new Error(message),{status:400});}
function parseOrigins(v) {
  if (!Array.isArray(v) || v.length>20) throw invalidSite('Укажи до 20 адресов сайтов.');
  return [...new Set(v.map(value=>{
    const raw=String(value||'').trim();let u;
    try { u=new URL(raw); } catch { throw invalidSite('Неверный адрес: '+raw); }
    if (u.username||u.password||u.pathname!=='/'||u.search||u.hash || !(['https:'].includes(u.protocol) || (u.protocol==='http:' && ['localhost','127.0.0.1'].includes(u.hostname)))) throw invalidSite('Используй HTTPS-домен без пути: '+raw);
    return u.origin;
  }))];
}
function allowedOrigin(site,origin) { try { return JSON.parse(site.origins).includes(origin); } catch {return false;} }
function originHeaders(origin){return {'Access-Control-Allow-Origin':origin,'Vary':'Origin','Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type','Access-Control-Max-Age':'600'};}
function readJson(req,max=8192){return new Promise((resolve,reject)=>{let chunks=[],size=0;req.on('data',buf=>{size+=buf.length;if(size>max){reject(Object.assign(new Error('Too large'),{status:413}));req.destroy();return;}chunks.push(buf);});req.on('end',()=>{try{resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))}catch{reject(Object.assign(new Error('Invalid JSON'),{status:400}))}});req.on('error',reject)});}
function cookie(req,k){const match=String(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith(k+'='));return match?match.slice(k.length+1):'';}
function safeEqual(a,b){const x=Buffer.from(String(a)),y=Buffer.from(String(b));return x.length===y.length && crypto.timingSafeEqual(x,y);}
const passwordSalt=crypto.randomBytes(16);
const expectedPass=crypto.scryptSync(password,passwordSalt,64);
function verifyPassword(value) { if(typeof value!=='string'||value.length>512) return false;return crypto.timingSafeEqual(crypto.scryptSync(value,passwordSalt,64),expectedPass);}
function sign(v){return crypto.createHmac('sha256',sessionSecret).update(v).digest('base64url');}
function createToken(){const raw=`${Date.now()+12*60*60*1000}.${crypto.randomBytes(20).toString('hex')}`;return `${raw}.${sign(raw)}`;}
function authorized(req){const token=cookie(req,'msa_admin');const p=token.split('.');if(p.length!==3||!safeEqual(p[2],sign(`${p[0]}.${p[1]}`)))return false;const until=Number(p[0]);return Number.isFinite(until)&&until>Date.now()&&until<Date.now()+12*60*60*1000+60000;}
function secureCookie(req){return env.TRUST_PROXY_HTTPS==='1'||req.socket.encrypted?' Secure;':'';}
function requestOriginOk(req){const origin=req.headers.origin;if(origin){try{const u=new URL(origin);const hostValue=req.headers['x-forwarded-host']&&env.TRUST_PROXY_HTTPS==='1'?req.headers['x-forwarded-host']:req.headers.host;return u.host===hostValue && (u.protocol==='https:' || (env.TRUST_PROXY_HTTPS!=='1'&&u.protocol==='http:'));}catch{return false;}}return !['cross-site'].includes(req.headers['sec-fetch-site']);}
const loginFailures = new Map();
function blockLogin(req){const k=req.socket.remoteAddress||'unknown';const now=Date.now(),entry=loginFailures.get(k);if(!entry || entry.reset<now){loginFailures.set(k,{n:0,reset:now+600000});return false;}return entry.n>=5;}
function badLogin(req){const k=req.socket.remoteAddress||'unknown';const entry=loginFailures.get(k);if(entry)entry.n++;}
function getDays(v){const d=Number(v);return [1,7,30,90].includes(d)?d:30;}
function since(days){return new Date(Date.now()-days*86400000).toISOString().slice(0,19).replace('T',' ');}
function metric(siteId,days){const date=since(days);
 const e=db.prepare(`SELECT COUNT(DISTINCT visitor_id) visitors,COUNT(DISTINCT session_id) visits,COUNT(*) pageviews
 FROM events WHERE site_id=? AND kind='view' AND created_at>=?`).get(siteId,date);
 const s=db.prepare(`SELECT AVG(visible_seconds) avg_seconds,COUNT(*) sessions,
 SUM(visible_seconds) total_seconds FROM sessions WHERE site_id=? AND started_at>=? AND views>0`).get(siteId,date);
 const medianRows=db.prepare('SELECT visible_seconds n FROM sessions WHERE site_id=? AND started_at>=? AND views>0 ORDER BY visible_seconds').all(siteId,date);
 const mid=Math.floor(medianRows.length/2);const med=medianRows.length?(medianRows.length%2?medianRows[mid].n:Math.round((medianRows[mid-1].n+medianRows[mid].n)/2)):0;
 return{visitors:e.visitors||0,visits:e.visits||0,pageviews:e.pageviews||0,avgSeconds:Math.round(s.avg_seconds||0),medianSeconds:med,totalSeconds:s.total_seconds||0};
}
function daily(siteId,days){const args=siteId?[siteId,since(days)]:[since(days)];const where=siteId?'site_id=? AND ':'';
 const views=db.prepare(`SELECT substr(created_at,1,10) day, COUNT(DISTINCT visitor_id) visitors, COUNT(DISTINCT session_id) visits FROM events WHERE ${where}kind='view' AND created_at>=? GROUP BY 1 ORDER BY 1`).all(...args);
 return views;
}
function detail(siteId,days){const s=since(days), base=metric(siteId,days);
 const pages=db.prepare("SELECT page,COUNT(*) views,COUNT(DISTINCT visitor_id) visitors FROM events WHERE site_id=? AND kind='view' AND created_at>=? GROUP BY page ORDER BY views DESC LIMIT 15").all(siteId,s);
 const sources=db.prepare("SELECT CASE WHEN referrer='' THEN 'Прямые переходы' WHEN referrer LIKE '%google.%' THEN 'Google' WHEN referrer LIKE '%yandex.%' THEN 'Яндекс' ELSE referrer END source, COUNT(*) visits FROM sessions WHERE site_id=? AND started_at>=? AND views>0 GROUP BY 1 ORDER BY visits DESC LIMIT 10").all(siteId,s);
 return {...base,daily:daily(siteId,days),pages,sources};
}
function staticFile(res,name,type){const f=path.join(ROOT,'public',name);const data=fs.readFileSync(f);res.writeHead(200,{'Content-Type':type,'X-Content-Type-Options':'nosniff','Cache-Control':name==='tracker.js'?'public,max-age=300':'no-store', 'Content-Security-Policy':name==='admin.html'?"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'":'default-src \'none\''});res.end(data);}
function handler(req,res){void (async()=>{
 const url=new URL(req.url,'http://local');const pathname=url.pathname;
 if(req.method==='GET' && (pathname==='/'||pathname==='/admin'))return staticFile(res,'admin.html','text/html; charset=utf-8');
 if(req.method==='GET' && pathname==='/admin.css')return staticFile(res,'admin.css','text/css; charset=utf-8');
 if(req.method==='GET' && pathname==='/admin.js')return staticFile(res,'admin.js','text/javascript; charset=utf-8');
 if(req.method==='GET' && pathname==='/tracker.js')return staticFile(res,'tracker.js','text/javascript; charset=utf-8');
 if(pathname==='/healthz'&&req.method==='GET')return reply(res,200,{ok:true});
 if(pathname==='/api/collect' && (req.method==='POST'||req.method==='OPTIONS')) {
   const site=getSite.get(url.searchParams.get('site'));const origin=req.headers.origin||'';
   if(!site || !origin || !allowedOrigin(site,origin))return reply(res,403,{error:'SITE_ORIGIN_NOT_ALLOWED'});
   const cors=originHeaders(origin);
   if(req.method==='OPTIONS'){res.writeHead(204,cors);return res.end();}
   const raw=await readJson(req,4096);
   if(!validUuid(raw.eventId)||!validUuid(raw.visitorId)||!validUuid(raw.sessionId)||!['view','heartbeat'].includes(raw.kind)||typeof raw.page!=='string'||raw.page.length>300||!raw.page.startsWith('/')||raw.page.includes('?')||raw.page.includes('#')||typeof raw.seconds!=='number'||!Number.isInteger(raw.seconds)||raw.seconds<0||raw.seconds>30||(raw.kind==='view'&&raw.seconds!==0)||(raw.kind==='heartbeat'&&raw.seconds<1))return reply(res,400,{error:'INVALID_EVENT'},cors);
   const ref=cleanText(raw.referrer||'',100).replace(/[^a-zA-Z0-9.:-]/g,'');
   db.exec('BEGIN');
   try{const ins=insertEvent.run(raw.eventId,site.id,raw.visitorId,raw.sessionId,raw.kind,raw.page,ref,raw.seconds);if(ins.changes)insertSession.run(site.id,raw.sessionId,raw.visitorId,raw.kind==='view'?1:0,raw.kind==='heartbeat'?raw.seconds:0,ref);db.exec('COMMIT');}
   catch(e){db.exec('ROLLBACK');throw e;}
   return reply(res,202,{ok:true},cors);
 }
 if(pathname==='/api/admin/login' && req.method==='POST'){
   if(!requestOriginOk(req))return reply(res,403,{error:'BAD_ORIGIN'});
   if(blockLogin(req))return reply(res,429,{error:'TOO_MANY_ATTEMPTS'});
   const body=await readJson(req,2048);
   if(!verifyPassword(body?.password)){badLogin(req);return reply(res,401,{error:'WRONG_PASSWORD'});}
   loginFailures.delete(req.socket.remoteAddress||'unknown');
   res.setHeader('Set-Cookie',`msa_admin=${createToken()}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200;${secureCookie(req)}`);
   return reply(res,200,{ok:true});
 }
 if(pathname==='/api/admin/logout' && req.method==='POST'){
   if(!requestOriginOk(req))return reply(res,403,{error:'BAD_ORIGIN'});
   res.setHeader('Set-Cookie',`msa_admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0;${secureCookie(req)}`);
   return reply(res,200,{ok:true});
 }
 if(pathname.startsWith('/api/admin/')){
   if(!authorized(req))return reply(res,401,{error:'UNAUTHORIZED'});
   if(!requestOriginOk(req))return reply(res,403,{error:'BAD_ORIGIN'});
   const days=getDays(url.searchParams.get('days'));
   if(pathname==='/api/admin/sites' && req.method==='GET')return reply(res,200,{sites:listSites.all().map(s=>({...s,origins:JSON.parse(s.origins)}))});
   if(pathname==='/api/admin/summary'&&req.method==='GET'){
     const sites=listSites.all().map(s=>({id:s.id,title:s.title,...metric(s.id,days)}));
     return reply(res,200,{days,sites,daily:daily(null,days),totals:{visitorsAcrossSites:sites.reduce((a,x)=>a+x.visitors,0),visits:sites.reduce((a,x)=>a+x.visits,0),pageviews:sites.reduce((a,x)=>a+x.pageviews,0)}});
   }
   if(pathname==='/api/admin/details' && req.method==='GET'){
     const site=getSite.get(url.searchParams.get('site'));
     if(!site)return reply(res,404,{error:'SITE_NOT_FOUND'});
     return reply(res,200,{site:{id:site.id,title:site.title,origins:JSON.parse(site.origins)},days,...detail(site.id,days)});
   }
   if(pathname==='/api/admin/sites'&&req.method==='POST'){
     const body=await readJson(req,5000),id=body.id,title=cleanText(body.title,80);
     if(!validId(id)||!title.trim())return reply(res,400,{error:'INVALID_SITE'});
     const origins=parseOrigins(body.origins||[]);if(getSite.get(id))return reply(res,409,{error:'SITE_EXISTS'});
     createSite.run(id,title,JSON.stringify(origins));return reply(res,201,{ok:true});
   }
   if(pathname==='/api/admin/sites'&&req.method==='PUT'){
     const body=await readJson(req,5000),id=body.id,title=cleanText(body.title,80);
     if(!validId(id)||!getSite.get(id)||!title.trim())return reply(res,400,{error:'INVALID_SITE'});
     const origins=parseOrigins(body.origins||[]);updateSite.run(title,JSON.stringify(origins),id);return reply(res,200,{ok:true});
   }
 }
 reply(res,404,{error:'NOT_FOUND'});
 })().catch(error=>{console.error('Request failed:',error);if(!res.headersSent)reply(res,error.status||500,{error:error.status===400?(error.message||'BAD_REQUEST'):error.status?'BAD_REQUEST':'SERVER_ERROR'});else res.end();});}

const server=http.createServer(handler);
server.listen(port,host,()=>console.log(`Analytics admin listening on http://${host}:${port}`));
process.on('SIGINT',()=>{db.close();server.close();process.exit(0)});
process.on('SIGTERM',()=>{db.close();server.close();process.exit(0)});
