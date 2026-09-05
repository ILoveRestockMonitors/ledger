/* Shared motion enhancement for current and newly rendered Ledger routes. */
(()=>{
 const root=document.documentElement,key='ledger-motion-paused';
 try{root.dataset.motionPaused=String(localStorage.getItem(key)==='true');}catch{}
 const button=document.createElement('button');button.className='btn btn-ghost motion-toggle';
 document.querySelector('.sidebar-foot').append(button);
 function label(){const paused=root.dataset.motionPaused==='true';button.textContent=paused?'Resume animations':'Pause animations';button.setAttribute('aria-pressed',String(paused));}
 button.onclick=()=>{root.dataset.motionPaused=String(root.dataset.motionPaused!=='true');try{localStorage.setItem(key,root.dataset.motionPaused);}catch{}label();};label();
 addEventListener('storage',e=>{if(e.key===key){root.dataset.motionPaused=String(e.newValue==='true');label();}});
 const viewport=new IntersectionObserver(entries=>entries.forEach(e=>e.target.classList.toggle('motion-visible',e.isIntersecting)),{threshold:.02});
 let sequence=0,queued=false;
 function enhance(){
  queued=false;
  document.querySelectorAll('#sidebar,#view .card,#view .subscription-row,#view .review-strip').forEach(el=>{
   if(el.classList.contains('motion-surface'))return;
   el.classList.add('motion-surface');
   const tint=document.createElement('span');tint.className='motion-tint';tint.setAttribute('aria-hidden','true');tint.style.setProperty('--motion-delay',-(sequence++%7)*2+'s');el.prepend(tint);viewport.observe(el);
  });
  document.querySelectorAll('.ar-bubble,.ar-ring,.ar-account,.ar-goal,.ar-delta,button.icon-button,button.owner-avatar,.ar-range button,.segmented button,.swatch,button.pill,a.pill,[role="button"].pill,.heat-cell[role="button"],.btn-primary,#mobile-add').forEach(el=>el.classList.add('motion-bubble'));
 }
 const observer=new MutationObserver(records=>{
  for(const record of records)for(const node of record.removedNodes)if(node.nodeType===1){if(node.classList.contains('motion-surface'))viewport.unobserve(node);node.querySelectorAll('.motion-surface').forEach(el=>viewport.unobserve(el));}
  if(!queued){queued=true;requestAnimationFrame(enhance);}
 });
 observer.observe(document.getElementById('view'),{childList:true,subtree:true});
 observer.observe(document.getElementById('modal-root'),{childList:true,subtree:true});enhance();
})();
