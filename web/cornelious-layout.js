/* Local, theme-independent card arrangement for Cornelious only. */
(()=>{
 const root=document.documentElement,storeKey='ledger-cornelious-card-order-v1';
 let saved=[];try{const v=JSON.parse(localStorage.getItem(storeKey)||'[]');if(Array.isArray(v))saved=v.filter(x=>typeof x==='string');}catch{}
 let pending,drag,ghost,drop,scrollFrame=0,status,reset;
 const enabled=()=>root.dataset.reviewMode==='aurora';
 const cards=()=>Array.from(document.querySelectorAll('.ar-grid>.card[data-corn-card]'));
 const key=c=>c.dataset.arCard||(c.matches('.ar-hero')?'worth':c.matches('.ar-month-budget')?'budget':c.querySelector('.ar-accts')?'accounts':c.querySelector('.ar-constellation')?'categories':c.querySelector('#arCategory')?'category-detail':c.matches('.ar-review')?'review':c.matches('.ar-rent-free')?null:'summary');
 const ordered=()=>cards().sort((a,b)=>{const rank=c=>saved.includes(c.dataset.cornCard)?saved.indexOf(c.dataset.cornCard):saved.length+cards().indexOf(c);return rank(a)-rank(b);});
 function announce(text){if(status)status.textContent=text;}
 function apply(){cards().forEach(c=>c.style.setProperty('--corn-order',String(saved.includes(c.dataset.cornCard)?saved.indexOf(c.dataset.cornCard):saved.length+cards().indexOf(c))));if(reset)reset.hidden=!saved.length;}
 function persist(){try{localStorage.setItem(storeKey,JSON.stringify(saved));}catch{announce('Layout changed. Browser storage is unavailable, so it will not survive a reload.');}apply();}
 function cleanup(){
  if(pending){clearTimeout(pending.timer);pending=null;}
  cancelAnimationFrame(scrollFrame);scrollFrame=0;
  drag?.card.classList.remove('corn-drag-source');drop?.classList.remove('corn-drop-target');ghost?.remove();ghost=null;drop=null;drag=null;root.classList.remove('corn-layout-dragging');
 }
 function commit(card,target,after=false){const list=ordered().map(c=>c.dataset.cornCard),id=card.dataset.cornCard;list.splice(list.indexOf(id),1);let pos=list.indexOf(target.dataset.cornCard);if(after)pos++;list.splice(Math.max(0,pos),0,id);saved=list;persist();announce('Card moved. Layout saved.');}
 function track(x,y){
  if(!drag)return;drag.x=x;drag.y=y;ghost.style.left=(x-drag.dx)+'px';ghost.style.top=(y-drag.dy)+'px';
  const hit=document.elementsFromPoint(x,y).map(e=>e.closest?.('.ar-grid>.card[data-corn-card]')).find(c=>c&&c!==drag.card&&!c.hidden);
  if(hit!==drop){drop?.classList.remove('corn-drop-target');drop=hit||null;drop?.classList.add('corn-drop-target');}
 }
 function scroll(){if(!drag)return;const y=drag.y;const amount=y<65?-12:y>innerHeight-65?12:0;if(amount){window.scrollBy(0,amount);track(drag.x,drag.y);}scrollFrame=requestAnimationFrame(scroll);}
 function begin(p){
  if(pending!==p||!enabled()||!p.card.isConnected)return;pending=null;
  const r=p.card.getBoundingClientRect();drag={...p,dx:p.x-r.left,dy:p.y-r.top};
  ghost=document.createElement('div');ghost.className='corn-drag-preview';ghost.setAttribute('aria-hidden','true');ghost.textContent=p.handle.getAttribute('aria-label').replace(/^Move /,'');ghost.style.width=Math.min(r.width,320)+'px';
  // A small label leaves the destination card visible while dragging.
  drag.dx=Math.min(drag.dx,120);drag.dy=22;document.body.append(ghost);p.card.classList.add('corn-drag-source');root.classList.add('corn-layout-dragging');track(p.x,p.y);scrollFrame=requestAnimationFrame(scroll);announce('Dragging card. Release over another card to move it. Escape cancels.');
 }
 function setup(){
  if(!enabled()){cleanup();return;}
  document.querySelectorAll('.ar-grid>.card').forEach(c=>{
   const id=key(c);if(!id)return;c.dataset.cornCard=id;
   if(c.querySelector('.corn-drag-handle'))return;
   const title=c.querySelector('h3,.ar-eyebrow')?.textContent.trim()||'dashboard card';
   const h=document.createElement('button');h.type='button';h.className='corn-drag-handle';h.textContent='⠿';h.setAttribute('aria-label','Move '+title);h.title='Hold and drag to move. Or focus and use arrow keys.';
   h.addEventListener('pointerdown',e=>{if(!enabled()||e.button!==0)return;cleanup();h.setPointerCapture(e.pointerId);const p={card:c,handle:h,pointer:e.pointerId,x:e.clientX,y:e.clientY};pending=p;p.timer=setTimeout(()=>begin(p),300);e.preventDefault();});
   h.addEventListener('pointermove',e=>{if(pending&&Math.hypot(e.clientX-pending.x,e.clientY-pending.y)>9){clearTimeout(pending.timer);pending=null;}if(drag){track(e.clientX,e.clientY);e.preventDefault();}});
   h.addEventListener('pointerup',()=>{if(drag&&drop)commit(drag.card,drop);cleanup();});
   h.addEventListener('pointercancel',cleanup);h.addEventListener('lostpointercapture',cleanup);
   h.addEventListener('keydown',e=>{if(!enabled())return;if(e.key==='Escape'){cleanup();return;}if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const list=ordered().filter(c=>!c.hidden),i=list.indexOf(c),forward=['ArrowDown','ArrowRight'].includes(e.key),other=list[i+(forward?1:-1)];if(other)commit(c,other,forward);});
   c.append(h);
  });
  const welcome=document.querySelector('.ar-welcome');
  if(welcome&&!welcome.querySelector('.corn-reset-layout')){reset=document.createElement('button');reset.type='button';reset.className='corn-reset-layout btn btn-ghost';reset.textContent='Reset layout';reset.onclick=()=>{cleanup();saved=[];persist();announce('Default layout restored.');};welcome.append(reset);}
  if(!status){status=document.createElement('div');status.className='corn-layout-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');document.body.append(status);}
  apply();
 }
 let queued=false;const schedule=()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;setup();});};
 const view=document.querySelector('#view');if(view)new MutationObserver(schedule).observe(view,{childList:true,subtree:true});
 new MutationObserver(setup).observe(root,{attributes:true,attributeFilter:['data-review-mode']});
 window.addEventListener('blur',cleanup);document.addEventListener('keydown',e=>{if(e.key==='Escape')cleanup();});
 window.addEventListener('storage',e=>{if(e.key!==storeKey)return;try{const v=JSON.parse(e.newValue||'[]');if(Array.isArray(v)){saved=v.filter(x=>typeof x==='string');apply();}}catch{}});
 setup();
})();
