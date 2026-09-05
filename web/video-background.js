/* Local generated video only; API credentials never enter the browser. */
(async()=>{
 let config;try{const r=await fetch('/sarah-background.json');if(!r.ok)return;config=await r.json();}catch{return;}
 if(typeof config.video!=='string'||!/^\/[a-zA-Z0-9/_-]+\.mp4$/.test(config.video))return;
 const root=document.documentElement,reduced=matchMedia('(prefers-reduced-motion:reduce)');
 const layer=document.createElement('div');layer.className='sarah-video-layer';layer.setAttribute('aria-hidden','true');
 const video=document.createElement('video');video.muted=true;video.loop=true;video.playsInline=true;video.preload='none';video.poster='/sarah-stream.png';video.tabIndex=-1;layer.append(video);document.body.append(layer);
 let failed=false,request=0;
 function allowed(){return !failed&&root.dataset.reviewMode==='custom'&&root.dataset.motionPaused!=='true'&&!reduced.matches&&!document.hidden;}
 async function sync(){const id=++request;if(!allowed()){video.pause();layer.classList.remove('playing');return;}if(!video.getAttribute('src'))video.src=config.video;try{await video.play();if(id===request&&allowed())layer.classList.add('playing');}catch{layer.classList.remove('playing');}}
 video.addEventListener('error',()=>{failed=true;layer.classList.remove('playing');});
 new MutationObserver(sync).observe(root,{attributes:true,attributeFilter:['data-review-mode','data-motion-paused']});
 reduced.addEventListener('change',sync);document.addEventListener('visibilitychange',sync);sync();
})();
