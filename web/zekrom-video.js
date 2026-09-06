/* Cornelious dark-mode ambient video, with the existing still as fallback. */
(()=>{
 const root=document.documentElement,reduced=matchMedia('(prefers-reduced-motion:reduce)');
 let video,layer,failed=false,request=0;
 const allowed=()=>!failed&&root.dataset.reviewMode==='aurora'&&root.dataset.theme==='dark'&&root.dataset.motionPaused!=='true'&&!reduced.matches&&!document.hidden;
 async function sync(){
  const id=++request;
  if(!allowed()){video?.pause();layer?.classList.remove('playing');return;}
  if(!video){
   layer=document.createElement('div');layer.className='cornelious-video-layer';layer.setAttribute('aria-hidden','true');
   video=document.createElement('video');video.muted=true;video.loop=true;video.playsInline=true;video.preload='none';video.poster='/zekrom-storm-background-v1.png';video.tabIndex=-1;video.src='/zekrom-storm-loop.mp4';
   video.addEventListener('error',()=>{failed=true;video.pause();layer.classList.remove('playing');});
   layer.append(video);document.body.append(layer);
  }
  if(root.dataset.mobileBusy==='true'){video.pause();return;}
  try{await video.play();if(id===request&&allowed()&&root.dataset.mobileBusy!=='true')layer.classList.add('playing');else if(!allowed()||root.dataset.mobileBusy==='true')video.pause();}catch{layer.classList.remove('playing');}
 }
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['data-review-mode','data-theme','data-motion-paused','data-mobile-busy']});
 reduced.addEventListener('change',sync);document.addEventListener('visibilitychange',sync);sync();
})();
