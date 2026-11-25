/* Unified Style & Layout selector (Clean / Cornelious / Sarah × Modern / Classic). */
(()=>{
 const root=document.documentElement,key='ledger-review-mode',motion=matchMedia('(prefers-reduced-motion:reduce)');
 const VALID=new Set(['aurora','custom','bubbles']);
 let mode='aurora',activeTransition,origin;
 try{const saved=localStorage.getItem(key);if(VALID.has(saved))mode=saved;}catch{}
 root.dataset.reviewMode=mode;

 const OPTIONS=[
  ['bubbles:new','Clean · Bubbles'],
  ['aurora:new','Cornelious'],
  ['custom:new','Sarah'],
  ['bubbles:classic','Clean · Classic'],
  ['aurora:classic','Cornelious · Classic'],
  ['custom:classic','Sarah · Classic'],
 ];
 const optionsHtml=OPTIONS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
 const currentLayout=()=>root.dataset.layout==='classic'?'classic':'new';
 const currentPreset=()=>`${mode}:${currentLayout()}`;

 const control=document.createElement('select');
 control.id='arPalette';
 control.className='input ar-palette';
 control.setAttribute('aria-label','Style and layout');
 control.title='Switch style and layout';
 control.innerHTML=optionsHtml;
 control.value=currentPreset();
 const topbar=document.getElementById('topbar');
 const themeAnchor=document.querySelector('[aria-label="Switch light / dark"]');
 if(topbar){
  if(themeAnchor&&themeAnchor.parentElement===topbar)topbar.insertBefore(control,themeAnchor);
  else topbar.appendChild(control);
 }

 function syncSettings(){
  const palette=document.getElementById('setting-palette');
  if(!palette)return;
  if(!palette.dataset.v2Palette){
   palette.removeAttribute('data-pref');
   palette.dataset.v2Palette='true';
   palette.innerHTML=optionsHtml;
   const label=document.querySelector('label[for="setting-palette"]');
   if(label)label.textContent='Style & layout';
   const fontLink=document.querySelector('[data-action="page"][data-id="typography"]');
   if(fontLink){const value=document.createElement('span');value.id='palette-font';value.className='small muted';fontLink.replaceWith(value);}
   const swatches=document.querySelector('.swatches');
   if(swatches){const lbl=swatches.previousElementSibling;if(lbl?.textContent==='Your accent color')lbl.remove();swatches.remove();}
   const note=palette.closest('.card')?.querySelector('.quiet-note');
   if(note)note.textContent='Choose Clean, Cornelious, or Sarah in Modern or Classic layout. Appearance and spacing save across devices.';
  }
  const preset=currentPreset();
  if(palette.value!==preset)palette.value=preset;
  const font=document.getElementById('palette-font');
  const fontLabel=mode==='custom'?'Lora · Sarah':mode==='bubbles'?'Manrope · Clean':'Manrope · Cornelious';
  if(font&&font.textContent!==fontLabel)font.textContent=fontLabel;
 }

 new MutationObserver(syncSettings).observe(document.getElementById('view'),{childList:true,subtree:true});

 function announce(){
  const preset=currentPreset();
  if(control.value!==preset)control.value=preset;
  syncSettings();
  root.style.setProperty('--font',mode==='custom'?"'Lora',Georgia,serif":"'Manrope',system-ui,sans-serif",'important');
  const logo=document.querySelector('.logo-sub');
  if(logo)logo.textContent=mode==='custom'?'Sarah':mode==='bubbles'?'Clean':'Cornelious';
  if(parent!==window)parent.postMessage({type:'review-appearance-state',mode,layout:currentLayout(),theme:root.dataset.theme},location.origin);
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
   wash.animate([{opacity:0},{opacity:.28,offset:.25},{opacity:0}],{duration:matchMedia('(max-width:700px)').matches?280:520,easing:'ease-out'}).onfinish=()=>wash.remove();
   return;
  }
  const transition=document.startViewTransition(update);activeTransition=transition;
  transition.ready.then(()=>{
   if(motion.matches){transition.skipTransition();return;}
   root.animate({clipPath:[`circle(0px at ${point.x}px ${point.y}px)`,`circle(${radius}px at ${point.x}px ${point.y}px)`],filter:['saturate(1.15)','saturate(1)']},{duration:480,easing:'cubic-bezier(.22,.8,.2,1)',pseudoElement:'::view-transition-new(root)'});
  }).catch(()=>{});
  transition.finished.finally(()=>{if(activeTransition===transition)activeTransition=null;}).catch(()=>{});
 }

 function setMode(value,save=true){
  const next=VALID.has(value)?value:'aurora';
  if(next===mode){announce();return;}
  reveal(()=>{
   mode=next;root.dataset.reviewMode=mode;
   if(save)try{localStorage.setItem(key,mode);}catch{}
   originalComfort({});announce();
  });
 }

 async function applyPreset(value){
  const [nextMode,nextLayout]=String(value||'aurora:new').split(':');
  const targetMode=VALID.has(nextMode)?nextMode:'aurora';
  const targetLayout=nextLayout==='classic'?'classic':'new';
  if(targetMode!==mode)setMode(targetMode,true);
  if(targetLayout!==currentLayout()&&typeof window.LedgerSetLayout==='function'){
   await window.LedgerSetLayout(targetLayout);
  }
  announce();
 }

 document.addEventListener('change',e=>{
  if(e.target.id==='setting-palette'||e.target===control){
   applyPreset(e.target.value).catch(err=>typeof toast==='function'&&toast(err.message||'Could not switch style.','err'));
  }
 });
 control.addEventListener('pointerdown',e=>{origin={x:e.clientX,y:e.clientY};});

 const originalComfort=applyComfort;
 applyComfort=config=>{
  const pref=config.theme||comfort.config.theme||'system';
  const next=pref==='system'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):pref;
  const update=()=>{originalComfort(config);announce();};
  if(mode==='custom'&&comfort.config.theme&&next!==root.dataset.theme)reveal(update);else update();
 };

 new MutationObserver(announce).observe(root,{attributes:true,attributeFilter:['data-layout']});
 window.LedgerStyle={getPreset:currentPreset,applyPreset,sync:announce};
 announce();
})();
