/* Tiny standalone first-party analytics tracker: page views + visible-tab time.
   No IP, cookies, fingerprinting, external analytics or user content. */
(()=>{'use strict';
 const script=document.currentScript;
 if(!script)return;
 const site=script.dataset.site;
 if(!/^[a-z0-9-]{2,40}$/.test(site||''))return;
 const base=new URL(script.src).origin;
 const endpoint=base+'/api/collect?site='+encodeURIComponent(site);
 const key='msa:'+site+':';
 const params=new URLSearchParams(location.search);
 try{if(params.get('__analytics')==='off')localStorage.setItem(key+'optout','1');if(params.get('__analytics')==='on')localStorage.removeItem(key+'optout');if(localStorage.getItem(key+'optout')==='1')return;}catch{}
 const random=()=>crypto.randomUUID();
 const getStorage=(storage,k)=>{try{return storage.getItem(k)}catch{return null}};
 const setStorage=(storage,k,v)=>{try{storage.setItem(k,v)}catch{}};
 const visitor=getStorage(localStorage,key+'visitor')||random();setStorage(localStorage,key+'visitor',visitor);
 const previous=Number(getStorage(sessionStorage,key+'last')||0);
 const session=previous>0 && Date.now()-previous<30*60*1000 && getStorage(sessionStorage,key+'session') || random();
 setStorage(sessionStorage,key+'session',session);setStorage(sessionStorage,key+'last',String(Date.now()));
 let referrer='';try{if(document.referrer){const u=new URL(document.referrer);if(u.origin!==location.origin)referrer=u.hostname;}}catch{}
 const page=()=>location.pathname.slice(0,300)||'/';
 function emit(kind,seconds=0,beacon=false){const body=JSON.stringify({eventId:random(),visitorId:visitor,sessionId:session,kind,page:page(),referrer,seconds});
   if(beacon&&navigator.sendBeacon){try{if(navigator.sendBeacon(endpoint,new Blob([body],{type:'text/plain'})))return;}catch{}}
   fetch(endpoint,{method:'POST',mode:'cors',headers:{'Content-Type':'text/plain'},body,keepalive:beacon,credentials:'omit'}).catch(()=>{});
 }
 emit('view');
 let visibleAt=document.visibilityState==='visible'?performance.now():null;
 function flush(beacon=false){if(visibleAt===null)return;const now=performance.now();let seconds=Math.floor(Math.max(0,now-visibleAt)/1000);visibleAt=now;if(seconds>=1){seconds=Math.min(seconds,30);emit('heartbeat',seconds,beacon);setStorage(sessionStorage,key+'last',String(Date.now()));}}
 setInterval(()=>{if(document.visibilityState==='visible')flush();},15000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'){flush(true);visibleAt=null;}else{visibleAt=performance.now();}});
 window.addEventListener('pagehide',()=>flush(true));
})();
