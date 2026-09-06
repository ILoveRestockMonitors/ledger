/* Decorative layers are mounted only while Cornelious is selected. */
(()=>{
 'use strict';
 const root=document.documentElement;
 const studioToggle=document.querySelector('#live')&&document.querySelector('#theme');
 const studioPalette=studioToggle&&document.querySelector('#palette');
 function syncStudio(){
  if(!studioToggle)return;
  root.dataset.reviewMode=studioPalette.value;
  root.dataset.theme=studioToggle.textContent.includes('Light')?'dark':'light';
 }
 syncStudio();
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 const hover=matchMedia('(hover: hover) and (pointer: fine)');
 let background,effect,target,frame=0;
 const stop=()=>{cancelAnimationFrame(frame);frame=0;target=null;effect?.remove();effect=null;};
 const allowed=()=>root.dataset.reviewMode==='aurora'&&root.dataset.motionPaused!=='true'&&root.dataset.mobileBusy!=='true'&&!reduce.matches&&!document.hidden;
 function sync(){
  if(root.dataset.reviewMode==='aurora'&&!studioToggle){
   if(!background){background=document.createElement('div');background.className='cornelious-legend';background.setAttribute('aria-hidden','true');document.body.prepend(background);}
  }else{background?.remove();background=null;}
  if(!allowed())stop();
 }
 // Layered translucent ribbons form irregular fire tongues, without cast shadows.
 function paintFire(time,w,h){
  const canvas=effect.querySelector('canvas');
  const dpr=Math.min(devicePixelRatio||1,2);
  const width=Math.max(1,Math.round(w*dpr)),height=Math.max(1,Math.round(h*dpr));
  if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
  const ctx=canvas.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  if(effect.dataset.element!=='light')return;
  const t=time/1000,n=Math.min(22,Math.max(7,Math.round(w/22)));
  for(let i=0;i<n;i++){
   const seed=i*2.399,phase=(t/(1.6+(i%5)*.17)+i*.317)%1;
   const life=Math.pow(Math.sin(phase*Math.PI),1.8);
   const x=(i+.5)*w/n,base=h*.99;
   const tall=Math.min(h*.87,58)*( .5+.5*Math.sin(seed)*Math.sin(seed))*life;
   const breadth=Math.min(w/n*.9,15)*( .6+life*.4);
   const sway=Math.sin(t*3.4+seed)*breadth*.65;
   for(let layer=0;layer<3;layer++){
    const length=tall*(1-layer*.19),b=breadth*(1-layer*.29),tip=x+sway;
    const gradient=ctx.createLinearGradient(x,base,x,base-length-1);
    gradient.addColorStop(0,layer===2?'rgba(255,251,214,.96)':'rgba(255,191,57,.82)');
    gradient.addColorStop(.35,layer===2?'rgba(255,229,133,.85)':'rgba(246,119,15,.66)');
    gradient.addColorStop(.75,'rgba(226,83,7,.25)');gradient.addColorStop(1,'rgba(255,149,38,0)');
    ctx.globalAlpha=life;ctx.fillStyle=gradient;ctx.beginPath();ctx.moveTo(x-b,base);
    ctx.bezierCurveTo(x-b*1.1,base-length*.35,tip+b*.5,base-length*.52,tip,base-length);
    ctx.bezierCurveTo(tip+b*.15,base-length*.7,x+b*1.2,base-length*.28,x+b,base);
    ctx.closePath();ctx.fill();
   }
   const rise=(t*.55+i*.271)%1;
   ctx.globalAlpha=Math.sin(rise*Math.PI)*.65;
   ctx.fillStyle='#e8a339';ctx.beginPath();ctx.ellipse(x+Math.sin(t+seed)*5,base-rise*h,.65,1.3,0,0,Math.PI*2);ctx.fill();
  }
  ctx.globalAlpha=1;
 }
 function position(){
  if(!target?.isConnected||!allowed()){stop();return;}
  // Mode controls preview the destination, even before the user clicks.
  const toggle=target.matches('#btn-theme,#theme,[aria-label="Switch light / dark"]');
  effect.dataset.element=toggle?(root.dataset.theme==='dark'?'light':'dark'):root.dataset.theme;
  const label=target.closest('#sidebar')&&target.querySelector('.nav-label,.more-nav-text,.sidebar-button-label,.sidebar-collapse-label');
  const wordRect=label?.getBoundingClientRect();
  const r=wordRect?.width?wordRect:target.getBoundingClientRect();
  if(!r.width||!r.height){stop();return;}
  Object.assign(effect.style,{left:(r.left-5)+'px',top:(r.top-5)+'px',width:(r.width+10)+'px',height:(r.height+10)+'px'});
  paintFire(performance.now(),r.width+10,r.height+10);
  frame=requestAnimationFrame(position);
 }
 function show(button){
  if(!button||button.disabled||button.getAttribute('aria-disabled')==='true'||!allowed())return;
  if(target===button)return;
  stop();target=button;effect=document.createElement('div');effect.className='cornelious-element';effect.setAttribute('aria-hidden','true');
  effect.innerHTML='<svg viewBox="0 0 240 64" preserveAspectRatio="none" aria-hidden="true"><path class="cornelious-electric" d="M3 28 0 15 9 18 6 4 42 6 52 1 62 8 79 4 112 5 123 0 131 7 171 4 182 8 193 2 231 5 237 14 231 21 239 33 234 43 239 53 227 61 200 58 188 64 179 57 142 61 130 56 122 63 89 58 70 63 59 56 23 60 5 55 9 43 1 39 3 28"/><g transform="translate(0 0)"><g class="cornelious-fire" style="--flame-delay:-0.25s;--flame-duration:1.9s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g><g transform="translate(42 0)"><g class="cornelious-fire" style="--flame-delay:-1.1s;--flame-duration:2.2s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g><g transform="translate(84 0)"><g class="cornelious-fire" style="--flame-delay:-0.65s;--flame-duration:1.8s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g><g transform="translate(126 0)"><g class="cornelious-fire" style="--flame-delay:-1.65s;--flame-duration:2.1s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g><g transform="translate(168 0)"><g class="cornelious-fire" style="--flame-delay:-0.95s;--flame-duration:2.3s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g><g transform="translate(210 0)"><g class="cornelious-fire" style="--flame-delay:-1.4s;--flame-duration:2.0s"><path class="cornelious-flame-outer" d="M15 63 C3 63 -1 54 4 45 C7 40 9 37 7 30 C14 33 17 38 16 42 C24 33 18 26 23 18 C23 29 33 36 31 47 C36 43 36 39 35 36 C44 47 38 63 25 63 Z"/><path class="cornelious-flame-core" d="M17 61 C10 58 13 52 17 47 C19 44 21 42 21 38 C28 46 24 50 28 52 C31 57 25 62 17 61 Z"/></g></g></svg>';
  const fireCanvas=document.createElement('canvas');fireCanvas.className='cornelious-real-fire';effect.append(fireCanvas);
  // Appending inside a modal keeps the effect above its contents without stealing input.
  (button.closest('dialog')||document.body).append(effect);position();
 }
 const buttonFor=e=>e.target instanceof Element?e.target.closest('button,[role="button"],#sidebar .nav-link,#sidebar summary'):null;
 document.addEventListener('pointerover',e=>{if(hover.matches&&e.pointerType!=='touch')show(buttonFor(e));});
 document.addEventListener('pointerout',e=>{if(target?.contains(e.target)&&!target.contains(e.relatedTarget))stop();});
 document.addEventListener('focusin',e=>{const b=buttonFor(e);if(b?.matches(':focus-visible'))show(b);});
 document.addEventListener('focusout',stop);
 document.addEventListener('visibilitychange',sync);
 window.addEventListener('blur',stop);
 reduce.addEventListener('change',sync);
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['data-review-mode','data-motion-paused','data-mobile-busy']});
 if(studioToggle){
  new MutationObserver(syncStudio).observe(studioToggle,{childList:true,subtree:true,characterData:true});
  studioPalette.addEventListener('change',syncStudio);
  window.addEventListener('message',syncStudio);
 }
 sync();
})();
