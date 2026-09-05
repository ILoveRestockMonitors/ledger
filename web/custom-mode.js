/* Original Ledger colors on the Aurora layout. Appearance stays local to this review. */
(()=>{
 const root=document.documentElement,key='ledger-review-mode',motion=matchMedia('(prefers-reduced-motion:reduce)');
 let mode='aurora',activeTransition,origin;
 try{mode=localStorage.getItem(key)==='custom'?'custom':'aurora';}catch{}
 root.dataset.reviewMode=mode;
 const control=document.createElement('select');
 control.id='arPalette';control.className='input ar-palette';control.setAttribute('aria-label','Color mode');
 control.innerHTML='<option value="aurora">Cornelious</option><option value="custom">Sarah</option>';
 control.value=mode;document.getElementById('topbar').insertBefore(control,document.querySelector('[aria-label="Switch light / dark"]'));
 function syncSettings(){
  const palette=document.getElementById('setting-palette');
  if(!palette)return;
  if(!palette.dataset.v2Palette){
   palette.removeAttribute('data-pref');palette.dataset.v2Palette='true';
   palette.innerHTML=control.innerHTML;
   const label=document.querySelector('label[for="setting-palette"]');if(label)label.textContent='Palette';
   const fontLink=document.querySelector('[data-action="page"][data-id="typography"]');
   if(fontLink){const value=document.createElement('span');value.id='palette-font';fontLink.replaceWith(value);}
   const swatches=document.querySelector('.swatches');
   if(swatches){const label=swatches.previousElementSibling;if(label?.textContent==='Your accent color')label.remove();swatches.remove();}
   const note=palette.closest('.card')?.querySelector('.quiet-note');if(note)note.textContent='Palette and font stay on this browser. Appearance and spacing save across your devices.';
  }
  if(palette.value!==mode)palette.value=mode;
  const font=document.getElementById('palette-font'),value=mode==='custom'?'Lora · Sarah':'Manrope · Cornelious';
  if(font&&font.textContent!==value)font.textContent=value;
 }
 new MutationObserver(syncSettings).observe(document.getElementById('view'),{childList:true,subtree:true});
 document.addEventListener('change',e=>{if(e.target.id==='setting-palette')setMode(e.target.value);});
 function announce(){
  control.value=mode;syncSettings();
  root.style.setProperty('--font',mode==='custom'?"'Lora',Georgia,serif":"'Manrope',system-ui,sans-serif",'important');
  const logo=document.querySelector('.logo-sub');if(logo)logo.textContent=mode==='custom'?'Sarah':'Cornelious';
  if(parent!==window)parent.postMessage({type:'review-appearance-state',mode,theme:root.dataset.theme},location.origin);
 }
 function reveal(update){
  activeTransition?.skipTransition();
  if(motion.matches||document.visibilityState==='hidden'){update();return;}
  const box=control.getBoundingClientRect(),point=origin||{x:box.x+box.width/2,y:box.y+box.height/2};origin=null;
  const radius=Math.hypot(Math.max(point.x,innerWidth-point.x),Math.max(point.y,innerHeight-point.y));
  if(!document.startViewTransition||matchMedia('(max-width:700px)').matches){
   update();
   const wash=document.createElement('div');wash.className='ar-custom-wash';wash.setAttribute('aria-hidden','true');
   wash.style.setProperty('--origin-x',point.x+'px');wash.style.setProperty('--origin-y',point.y+'px');document.body.append(wash);
   wash.animate([{opacity:0},{opacity:.32,offset:.25},{opacity:0}],{duration:matchMedia('(max-width:700px)').matches?280:650,easing:'ease-out'}).onfinish=()=>wash.remove();
   return;
  }
  const transition=document.startViewTransition(update);activeTransition=transition;
  transition.ready.then(()=>{
   if(motion.matches){transition.skipTransition();return;}
   root.animate({clipPath:[`circle(0px at ${point.x}px ${point.y}px)`,`circle(${radius}px at ${point.x}px ${point.y}px)`],filter:['saturate(1.3)','saturate(1)']},{duration:680,easing:'cubic-bezier(.22,.8,.2,1)',pseudoElement:'::view-transition-new(root)'});
  }).catch(()=>{});
  transition.finished.finally(()=>{if(activeTransition===transition)activeTransition=null;}).catch(()=>{});
 }
 function setMode(value,save=true){
  const next=value==='custom'?'custom':'aurora';
  if(next===mode){announce();return;}
  reveal(()=>{
   mode=next;root.dataset.reviewMode=mode;
   if(save)try{localStorage.setItem(key,mode);}catch{}
   // Reapply accent preferences when returning to Aurora.
   originalComfort({});announce();
  });
 }
 const originalComfort=applyComfort;
 applyComfort=config=>{
  const pref=config.theme||comfort.config.theme||'system';
  const next=pref==='system'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):pref;
  const update=()=>{originalComfort(config);announce();};
  if(mode==='custom'&&comfort.config.theme&&next!==root.dataset.theme)reveal(update);else update();
 };
 control.addEventListener('change',()=>setMode(control.value));
 document.addEventListener('pointerdown',e=>{
  if(e.target.closest('#arPalette,#btn-theme,[aria-label="Switch light / dark"],#setting-theme'))origin={x:e.clientX,y:e.clientY};
 });
 addEventListener('storage',e=>{if(e.key===key)setMode(e.newValue,false);});
 addEventListener('message',e=>{
  if(e.origin!==location.origin||e.source!==parent)return;
  if(e.data?.type==='review-mode')setMode(e.data.mode);
  if(e.data?.type==='review-request-appearance')announce();
 });
 motion.addEventListener('change',()=>{if(motion.matches){activeTransition?.skipTransition();document.querySelectorAll('.ar-custom-wash').forEach(el=>el.remove());}});
 announce();
})();
