/* Cornelious-only, control-bound lightning. No input interception or layout changes. */
(()=>{
 'use strict';
 const root=document.documentElement,reduce=matchMedia('(prefers-reduced-motion: reduce)'),fine=matchMedia('(hover: hover) and (pointer: fine)');
 const controls='button,a[href],summary,[role="button"],[role="link"],[role="tab"],[data-action]';
 let canvas,ctx,raf=0,bolts=[],next=0,last=0,width=0,height=0,target=null,hovered=false;
 const enabled=()=>root.dataset.reviewMode==='aurora'&&root.dataset.theme==='dark'&&root.dataset.motionPaused!=='true'&&root.dataset.mobileBusy!=='true'&&!reduce.matches&&fine.matches&&!document.hidden;
 const actionable=node=>{const el=node instanceof Element?node.closest(controls):null;return el&&!el.matches(':disabled,[aria-disabled="true"]')?el:null;};
 const isActive=()=>enabled()&&hovered;
 function clear(){cancelAnimationFrame(raf);raf=0;bolts=[];canvas?.remove();canvas=null;ctx=null;next=0;}
 function resize(){
  if(!canvas||!target?.isConnected)return;
  const r=target.getBoundingClientRect();
  Object.assign(canvas.style,{inset:'auto',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px',borderRadius:getComputedStyle(target).borderRadius});
  if(width===r.width&&height===r.height)return;
  width=r.width;height=r.height;
  const dpr=Math.min(devicePixelRatio||1,1.5);
  canvas.width=Math.ceil(width*dpr);canvas.height=Math.ceil(height*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);bolts=[];next=0;
 }
 // Midpoint displacement gives long bends plus fine, irregular electrical forks.
 function trace(a,b,roughness,depth=6){
  if(!depth)return[a,b];
  const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;
  const shift=(Math.random()-.5)*roughness;
  const m={x:(a.x+b.x)/2-dy/len*shift,y:(a.y+b.y)/2+dx/len*shift};
  return trace(a,m,roughness*.58,depth-1).slice(0,-1).concat(trace(m,b,roughness*.58,depth-1));
 }
 // Angular segments and stronger fine displacement produce crisp electrical zigzags.
 function path(points){
  const p=new Path2D();p.moveTo(points[0].x,points[0].y);
  for(const point of points.slice(1))p.lineTo(point.x,point.y);
  return p;
 }
 function strike(now){
  const side=Math.random()<.5;
  const a={x:side?0:width,y:height*(.05+Math.random()*.45)};
  const b={x:width*(.2+Math.random()*.6),y:height*(.55+Math.random()*.4)};
  const points=trace(a,b,Math.min(width,height)*.5),branches=[];
  for(let i=9;i<56;i+=7){const v=points[i];const sign=Math.random()<.5?-1:1;const end={x:v.x+sign*(width*(.04+Math.random()*.16)),y:v.y+height*(.1+Math.random()*.25)};const branch=trace(v,end,height*.45,4);branches.push(path(branch));if(i%2)branches.push(path(trace(branch[9],{x:end.x+sign*width*.06,y:end.y-height*.3},height*.25,3)));}
  bolts.push({main:path(points),branches,born:now,duration:1500+Math.random()*800});
 }
 function paint(now){
  if(!enabled()||!target?.isConnected){clear();return;}
  resize();
  if(!width||!height){clear();return;}
  const active=isActive();
  if(active){last=now;if(now>=next){strike(now);next=now+700+Math.random()*650;}}
  const release=active?1:Math.max(0,1-(now-last)/550);
  ctx.clearRect(0,0,width,height);
  bolts=bolts.filter(b=>now-b.born<b.duration);
  for(const b of bolts){
   const age=(now-b.born)/b.duration;
   const envelope=Math.min(1,age/.16)*Math.pow(1-age,1.4)*release;
   ctx.globalAlpha=envelope*.52;ctx.lineCap='round';ctx.lineJoin='round';
   ctx.strokeStyle='#309fe9';ctx.lineWidth=3;ctx.shadowColor='#238fea';ctx.shadowBlur=12;ctx.stroke(b.main);
   ctx.shadowBlur=0;ctx.strokeStyle='#b9ebff';ctx.lineWidth=1.1;ctx.stroke(b.main);
   ctx.strokeStyle='#f3fbff';ctx.lineWidth=.45;ctx.stroke(b.main);
   ctx.globalAlpha=envelope*.3;ctx.strokeStyle='#89ccfa';ctx.lineWidth=.65;b.branches.forEach(p=>ctx.stroke(p));
  }
  ctx.globalAlpha=1;
  if(!active&&release===0){clear();return;}
  raf=requestAnimationFrame(paint);
 }
 function sync(){
  if(!enabled()){clear();return;}
  if(isActive()&&target&&!canvas){
   canvas=document.createElement('canvas');canvas.className='cornelious-storm';canvas.setAttribute('aria-hidden','true');
   (target.closest('dialog')||document.body).append(canvas);
   ctx=canvas.getContext('2d');if(!ctx){clear();return;}
   width=height=0;resize();last=performance.now();raf=requestAnimationFrame(paint);
  }
 }
 function choose(el){
  if(el&&el!==target){clear();target=el;}
  hovered=Boolean(el);sync();
 }
 document.addEventListener('pointerover',e=>choose(e.pointerType!=='touch'?actionable(e.target):null));
 document.addEventListener('pointerout',e=>choose(actionable(e.relatedTarget)));
 document.addEventListener('focusin',e=>choose(e.target instanceof Element&&e.target.matches(':focus-visible')?actionable(e.target):null));
 document.addEventListener('focusout',()=>choose(null));
 window.addEventListener('blur',()=>choose(null));
 window.addEventListener('resize',resize);
 document.addEventListener('visibilitychange',()=>choose(null));
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['data-review-mode','data-theme','data-motion-paused','data-mobile-busy']});
 reduce.addEventListener('change',sync);fine.addEventListener('change',sync);
})();
