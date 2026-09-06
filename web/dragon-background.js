/* Twin-dragon backdrop: an ivory dragon wreathed in fire for the light theme, an
   obsidian dragon wreathed in lightning for the dark one. The creature is an original
   design drawn as inline SVG; embers, flame and electricity are painted on one canvas.
   All motion honours prefers-reduced-motion, the sidebar pause control, and tab visibility. */
(()=>{
 const root=document.documentElement,reduced=matchMedia('(prefers-reduced-motion:reduce)'),fine=matchMedia('(hover:hover) and (pointer:fine)');
 const rand=(a,b)=>a+Math.random()*(b-a);

 const figure=`<svg class="dragon-figure" viewBox="0 0 720 1000" fill="none" aria-hidden="true" focusable="false">
  <defs>
   <linearGradient id="dgBody" x1=".1" y1="0" x2=".95" y2="1">
    <stop offset="0" style="stop-color:var(--d-scale-a)"/><stop offset=".44" style="stop-color:var(--d-scale-b)"/><stop offset="1" style="stop-color:var(--d-scale-c)"/>
   </linearGradient>
   <linearGradient id="dgWing" x1=".05" y1="1" x2=".95" y2="0">
    <stop offset="0" style="stop-color:var(--d-scale-b);stop-opacity:.62"/><stop offset="1" style="stop-color:var(--d-scale-c);stop-opacity:.12"/>
   </linearGradient>
   <linearGradient id="dgRing" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" style="stop-color:var(--d-ring-hot)"/><stop offset=".5" style="stop-color:var(--d-ring-mid)"/><stop offset="1" style="stop-color:var(--d-ring-out)"/>
   </linearGradient>
   <filter id="dgGlow" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="32"/></filter>
   <filter id="dgSoft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter>
   <filter id="dgHair" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.6"/></filter>

   <!-- Anatomy lives on three spines: a slim neck, a heavy torso, a tapering tail.
        Drawing every rim stroke before every fill leaves one clean outline around the union. -->
   <g id="dgSpines">
    <path id="dgNeck" d="M376 204C398 258 420 312 440 366C452 400 462 436 470 470"/>
    <path id="dgTorso" d="M470 470C486 522 504 578 522 634C534 668 546 686 556 700"/>
    <path id="dgTail" d="M556 700C570 748 582 800 590 852C596 896 598 932 596 962"/>
   </g>
   <g id="dgMass">
    <path d="M200 178C214 154 236 136 262 128C282 100 316 80 356 74C350 96 352 116 362 132C380 146 392 166 396 190C386 208 368 220 346 224C318 228 288 222 264 210C238 202 214 192 200 178Z"/>
    <path d="M344 78C372 58 404 46 438 42C416 62 398 84 386 108C372 96 356 86 344 78Z"/>
   </g>
  </defs>

  <!-- folded far wing, for depth -->
  <path d="M432 396C462 336 502 280 552 240C538 282 518 322 492 358C512 360 528 364 542 372C516 394 488 412 460 430C444 422 434 410 432 396Z" fill="url(#dgWing)" opacity=".5"/>

  <!-- the fire ring the tail carries -->
  <circle cx="590" cy="880" r="252" style="fill:var(--d-ring-mid)" opacity=".18" filter="url(#dgGlow)"/>
  <circle cx="590" cy="880" r="148" style="fill:var(--d-ring-hot)" opacity=".24" filter="url(#dgGlow)"/>
  <circle cx="590" cy="880" r="104" fill="none" stroke="url(#dgRing)" stroke-width="40" opacity=".95"/>
  <circle cx="590" cy="880" r="104" fill="none" style="stroke:var(--d-ring-hot)" stroke-width="8" opacity=".6" filter="url(#dgSoft)"/>

  <!-- outer rim, blurred, then crisp -->
  <g filter="url(#dgSoft)" style="stroke:var(--d-rim-soft);fill:var(--d-rim-soft)" stroke-linecap="round" stroke-linejoin="round" opacity=".72">
   <use href="#dgNeck" stroke-width="64" fill="none"/><use href="#dgTorso" stroke-width="112" fill="none"/><use href="#dgTail" stroke-width="58" fill="none"/>
   <use href="#dgMass" stroke-width="18"/>
  </g>
  <g style="stroke:var(--d-rim);fill:var(--d-rim);opacity:var(--d-rim-line,.9)" stroke-linecap="round" stroke-linejoin="round">
   <use href="#dgNeck" stroke-width="53" fill="none"/><use href="#dgTorso" stroke-width="99" fill="none"/><use href="#dgTail" stroke-width="45" fill="none"/>
   <use href="#dgMass" stroke-width="6"/>
  </g>
  <!-- body fill, drawn over the rim so only a hairline of it survives -->
  <g style="stroke:url(#dgBody);fill:url(#dgBody)" stroke-linecap="round" stroke-linejoin="round">
   <use href="#dgNeck" stroke-width="46" fill="none"/><use href="#dgTorso" stroke-width="92" fill="none"/><use href="#dgTail" stroke-width="38" fill="none"/>
   <use href="#dgMass" stroke-width="0"/>
  </g>

  <!-- brow, jawline and nostril -->
  <g style="stroke:var(--d-rim)" fill="none" stroke-width="2.4" opacity=".7" filter="url(#dgHair)">
   <path d="M224 168C252 168 282 176 306 190C326 202 342 216 352 230"/>
   <path d="M262 128C288 138 312 152 330 170"/>
   <path d="M210 174C218 170 228 168 238 168"/>
  </g>

  <!-- raised wing with finger bones -->
  <path d="M486 486C528 396 596 306 684 240C664 296 636 348 602 394C630 390 656 394 680 404C648 434 610 462 572 484C590 498 604 512 616 532C574 540 532 552 496 570C478 544 476 512 486 486Z" fill="url(#dgWing)"/>
  <g style="stroke:var(--d-rim)" fill="none" stroke-width="2.8" opacity=".66">
   <path d="M486 486C528 396 596 306 684 240"/>
   <path d="M492 512C536 462 574 430 614 402"/>
   <path d="M498 540C540 506 574 484 606 466"/>
   <path d="M506 566C544 544 574 528 600 518"/>
  </g>

  <ellipse id="dgRingAnchor" cx="590" cy="880" rx="104" ry="104" fill="none"/>
  <circle cx="286" cy="164" r="8.5" style="fill:var(--d-eye)"/>
  <circle cx="286" cy="164" r="23" style="fill:var(--d-eye)" opacity=".5" filter="url(#dgSoft)"/>
 </svg>`;

 const bg=document.createElement('div');
 bg.className='dragon-bg';bg.setAttribute('aria-hidden','true');
 bg.innerHTML=`<div class="dragon-layer dragon-sky"></div>
  <div class="dragon-layer dragon-cloud dragon-cloud-far"></div>
  <div class="dragon-layer dragon-haze"></div>
  <div class="dragon-layer dragon-cloud dragon-cloud-near"></div>
  <div class="dragon-layer dragon-rays"></div>
  <div class="dragon-aura"></div>
  ${figure}
  <canvas class="dragon-fx"></canvas>
  <div class="dragon-layer dragon-scrim"></div>`;
 document.body.prepend(bg);
 root.dataset.dragonBg='on';
 requestAnimationFrame(()=>bg.classList.add('ready'));

 const canvas=bg.querySelector('.dragon-fx'),ctx=canvas.getContext('2d'),anchor=bg.querySelector('#dgRingAnchor');
 let w=0,h=0,embers=[],motes=[],bolts=[],crackle=[],flash=0,nextBolt=0,nextCrackle=0,raf=0,last=0;
 let ring={x:0,y:0,r:0},emberSprite,moteSprite,emberRGB='255,168,74',boltRGB='255,214,150',comp='lighter',fxAlpha=.75;
 /* The backdrop sits under blurred glass cards, so every painted frame costs a re-blur.
    Thirty frames a second is plenty for embers and arcs. When frames still come back late,
    stepping the interval down is what actually helps, because it is the repaint rate rather
    than the particle count that drives the cost. */
 const GAPS=[1000/30,1000/20,1000/12];let gap=0,slow=0,quality=1;

 const paused=()=>reduced.matches||root.dataset.motionPaused==='true'||document.hidden;
 const light=()=>root.dataset.theme!=='dark';

 function sprite(rgb){
  const size=64,c=document.createElement('canvas');c.width=c.height=size;
  const g=c.getContext('2d'),r=size/2,grad=g.createRadialGradient(r,r,0,r,r,r);
  grad.addColorStop(0,`rgba(${rgb},1)`);grad.addColorStop(.3,`rgba(${rgb},.5)`);grad.addColorStop(1,`rgba(${rgb},0)`);
  g.fillStyle=grad;g.fillRect(0,0,size,size);return c;
 }

 function readTheme(){
  const cs=getComputedStyle(root);
  comp=cs.getPropertyValue('--d-fx-comp').trim()||'lighter';
  fxAlpha=parseFloat(cs.getPropertyValue('--d-fx-alpha'))||.75;
  emberRGB=cs.getPropertyValue('--d-ember').trim()||emberRGB;
  boltRGB=cs.getPropertyValue('--d-bolt').trim()||boltRGB;
  emberSprite=sprite(emberRGB);moteSprite=sprite(boltRGB);
  embers=[];motes=[];bolts=[];crackle=[];flash=0;
 }

 function measure(){
  const dpr=Math.min(1,devicePixelRatio||1);
  w=innerWidth;h=innerHeight;
  canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  const box=anchor?.getBoundingClientRect();
  ring=box&&box.width?{x:box.x+box.width/2,y:box.y+box.height/2,r:box.width/2}:{x:w*.86,y:h*.72,r:Math.min(w,h)*.16};
 }

 /* ---- light theme: embers lifting off the fire ring ---- */
 function spawnEmber(seed){
  const fromRing=Math.random()<.7;
  const a=rand(0,Math.PI*2),d=ring.r*rand(.55,1.25);
  const maxLife=rand(3.6,9);
  return {
   x:fromRing?ring.x+Math.cos(a)*d:rand(-40,w),
   y:fromRing?ring.y+Math.sin(a)*d*.8:h+rand(0,120),
   vx:rand(-16,26),vy:-rand(16,62),
   size:rand(6,26),phase:rand(0,Math.PI*2),sway:rand(6,20),
   life:seed?rand(0,maxLife):0,maxLife
  };
 }
 function drawEmbers(dt){
  const target=Math.round(Math.max(34,Math.min(120,w*h/20000))*quality);
  while(embers.length<target)embers.push(spawnEmber(embers.length<target-2));
  if(embers.length>target)embers.length=target;
  ctx.globalCompositeOperation=comp;
  for(const e of embers){
   e.life+=dt;
   if(e.life>=e.maxLife||e.y<-60){Object.assign(e,spawnEmber(false));continue;}
   e.phase+=dt*1.6;
   e.x+=(e.vx+Math.sin(e.phase)*e.sway)*dt;
   e.y+=e.vy*dt;
   ctx.globalAlpha=Math.sin(Math.PI*(e.life/e.maxLife))*fxAlpha;
   ctx.drawImage(emberSprite,e.x-e.size/2,e.y-e.size/2,e.size,e.size);
  }
  /* A slow plume over the ring keeps the fire itself alive between embers. */
  const beat=Math.sin(last/900),s=ring.r*(2.5+beat*.16);
  ctx.globalAlpha=.3+beat*.07;
  ctx.drawImage(emberSprite,ring.x-s/2,ring.y-s/2-ring.r*.45,s,s);
  ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
 }

 /* ---- dark theme: drifting motes, ring crackle, branching strikes ---- */
 function spawnMote(seed){
  const maxLife=rand(5,12);
  return {x:rand(-40,w+40),y:rand(-40,h+40),vx:rand(-12,10),vy:-rand(4,20),
   size:rand(4,14),phase:rand(0,Math.PI*2),sway:rand(3,11),life:seed?rand(0,maxLife):0,maxLife};
 }
 function jagged(x1,y1,x2,y2,depth,spread){
  let pts=[[x1,y1],[x2,y2]];
  for(let d=0;d<depth;d++){
   const next=[pts[0]];
   for(let i=0;i<pts.length-1;i++){
    const [ax,ay]=pts[i],[bx,by]=pts[i+1];
    const mx=(ax+bx)/2,my=(ay+by)/2,dx=bx-ax,dy=by-ay,len=Math.hypot(dx,dy)||1;
    const off=rand(-1,1)*len*spread;
    next.push([mx-dy/len*off,my+dx/len*off],pts[i+1]);
   }
   pts=next;
  }
  return pts;
 }
 function strike(){
  const a=rand(Math.PI*.55,Math.PI*1.35),reach=Math.max(w,h)*rand(.45,1.05);
  const sx=ring.x+Math.cos(a)*ring.r,sy=ring.y+Math.sin(a)*ring.r;
  const main=jagged(sx,sy,sx+Math.cos(a)*reach,sy+Math.sin(a)*reach,6,.24);
  const limbs=[];
  for(let i=0;i<Math.round(rand(1,4));i++){
   const p=main[Math.floor(rand(main.length*.25,main.length*.85))];
   const b=a+rand(-.9,.9);
   limbs.push(jagged(p[0],p[1],p[0]+Math.cos(b)*reach*rand(.18,.4),p[1]+Math.sin(b)*reach*rand(.18,.4),4,.3));
  }
  bolts.push({paths:[main,...limbs],life:0,ttl:rand(220,420)});
  flash=Math.min(.22,flash+rand(.08,.16));
 }
 function trace(pts,width,alpha,color){
  ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
  for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i][0],pts[i][1]);
  ctx.lineWidth=width;ctx.strokeStyle=color;ctx.globalAlpha=alpha;ctx.stroke();
 }
 function drawStorm(dt){
  const target=Math.round(Math.max(20,Math.min(70,w*h/38000))*quality);
  while(motes.length<target)motes.push(spawnMote(motes.length<target-2));
  if(motes.length>target)motes.length=target;
  ctx.globalCompositeOperation=comp;
  for(const m of motes){
   m.life+=dt;
   if(m.life>=m.maxLife){Object.assign(m,spawnMote(false));continue;}
   m.phase+=dt*1.1;
   m.x+=(m.vx+Math.sin(m.phase)*m.sway)*dt;m.y+=m.vy*dt;
   ctx.globalAlpha=Math.sin(Math.PI*(m.life/m.maxLife))*fxAlpha*.78;
   ctx.drawImage(moteSprite,m.x-m.size/2,m.y-m.size/2,m.size,m.size);
  }
  ctx.lineCap='round';ctx.lineJoin='round';

  if(last>nextCrackle){
   nextCrackle=last+rand(90,190);
   crackle=[];
   for(let i=0;i<Math.round(rand(2,5));i++){
    const a=rand(0,Math.PI*2),spanA=a+rand(.35,1.1);
    crackle.push(jagged(ring.x+Math.cos(a)*ring.r,ring.y+Math.sin(a)*ring.r,
     ring.x+Math.cos(spanA)*ring.r,ring.y+Math.sin(spanA)*ring.r,4,.22));
   }
  }
  for(const c of crackle){trace(c,4,.14,`rgb(${boltRGB})`);trace(c,1.2,.7,'#ffffff');}

  if(last>nextBolt){nextBolt=last+rand(2200,6800);strike();}
  for(let i=bolts.length-1;i>=0;i--){
   const b=bolts[i];b.life+=dt*1000;
   if(b.life>b.ttl){bolts.splice(i,1);continue;}
   const k=1-b.life/b.ttl,flicker=.55+Math.abs(Math.sin(b.life/26))*.45;
   for(const p of b.paths){
    trace(p,11,.1*k*flicker,`rgb(${boltRGB})`);
    trace(p,4,.34*k*flicker,`rgb(${boltRGB})`);
    trace(p,1.5,.95*k*flicker,'#ffffff');
   }
  }
  if(flash>.002){
   ctx.globalAlpha=flash;ctx.fillStyle=`rgb(${boltRGB})`;ctx.fillRect(0,0,w,h);
   flash*=Math.pow(.0016,dt);
  }
  ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
 }

 function frame(t){
  raf=requestAnimationFrame(frame);
  if(t-last<GAPS[gap]-1)return;
  const dt=Math.min(.05,(t-last)/1000)||.016;last=t;
  if(dt*1000>GAPS[gap]*1.6)slow++;else slow=Math.max(0,slow-1);
  if(slow>45){slow=0;if(quality>.4)quality*=.6;else if(gap<GAPS.length-1)gap++;}
  ctx.clearRect(0,0,w,h);
  light()?drawEmbers(dt):drawStorm(dt);
 }
 function still(){
  ctx.clearRect(0,0,w,h);
  /* A single held frame so the composition never looks empty when motion is off. */
  nextBolt=Infinity;
  if(light()){embers=Array.from({length:34},()=>spawnEmber(true));drawEmbers(0);}
  else{motes=Array.from({length:26},()=>spawnMote(true));drawStorm(0);}
 }
 function sync(){
  cancelAnimationFrame(raf);raf=0;
  if(paused()){still();return;}
  last=performance.now()-GAPS[gap];slow=0;nextBolt=last+rand(700,2200);nextCrackle=0;
  raf=requestAnimationFrame(frame);
 }

 /* ---- pointer parallax ---- */
 if(fine.matches){
  let queued=false,px=0,py=0;
  addEventListener('pointermove',e=>{
   if(paused())return;
   px=(e.clientX/innerWidth-.5)*-18;py=(e.clientY/innerHeight-.5)*-12;
   if(queued)return;queued=true;
   requestAnimationFrame(()=>{queued=false;bg.style.setProperty('--d-shift-x',px.toFixed(1)+'px');bg.style.setProperty('--d-shift-y',py.toFixed(1)+'px');});
  },{passive:true});
 }

 /* ---- optional Seedance render, same shape as the existing video backdrop ---- */
 let videoSync=()=>{};
 (async()=>{
  let config;try{const r=await fetch('/dragon-background.json');if(!r.ok)return;config=await r.json();}catch{return;}
  const valid=v=>typeof v==='string'&&/^\/[a-zA-Z0-9/_-]+\.mp4$/.test(v);
  if(!valid(config.light)&&!valid(config.dark))return;
  const video=document.createElement('video');
  video.className='dragon-video';video.muted=true;video.loop=true;video.playsInline=true;video.preload='none';video.tabIndex=-1;
  bg.insertBefore(video,canvas);
  let failed=false,request=0,source='';
  video.addEventListener('error',()=>{failed=true;video.classList.remove('playing');bg.classList.remove('video-playing');});
  async function play(){
   const id=++request,src=light()?config.light:config.dark;
   if(failed||paused()||!valid(src)){video.pause();video.classList.remove('playing');bg.classList.remove('video-playing');return;}
   if(source!==src){source=src;video.src=src;}
   try{await video.play();if(id===request){video.classList.add('playing');bg.classList.add('video-playing');}}
   catch{video.classList.remove('playing');bg.classList.remove('video-playing');}
  }
  videoSync=play;play();
 })();

 function refresh(){readTheme();measure();sync();videoSync();}
 new MutationObserver(refresh).observe(root,{attributes:true,attributeFilter:['data-theme','data-motion-paused']});
 addEventListener('resize',()=>{measure();if(paused())still();},{passive:true});
 addEventListener('orientationchange',refresh);
 document.addEventListener('visibilitychange',()=>{sync();videoSync();});
 reduced.addEventListener('change',refresh);
 refresh();
})();
