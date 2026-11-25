/* Mount subtle fading multi-color ambient bubbles for the Clean theme. */
(()=>{
 if(document.querySelector('.bubbles-bg'))return;
 const host=document.createElement('div');
 host.className='bubbles-bg';
 host.setAttribute('aria-hidden','true');
 // Carefully spaced positions, sizes, hues (blue, cyan, emerald, lavender, coral, amber, rose)
 const orbs=[
  {x:'14%',y:'18%',s:'260px',h:214,dur:'13s',delay:'-2s',dx:'18px',dy:'-16px'},
  {x:'42%',y:'12%',s:'210px',h:270,dur:'16s',delay:'-9s',dx:'-14px',dy:'18px'},
  {x:'78%',y:'16%',s:'290px',h:192,dur:'15s',delay:'-5s',dx:'-20px',dy:'14px'},
  {x:'91%',y:'44%',s:'240px',h:340,dur:'17s',delay:'-11s',dx:'-16px',dy:'-20px'},
  {x:'66%',y:'38%',s:'180px',h:158,dur:'12s',delay:'-3s',dx:'14px',dy:'16px'},
  {x:'26%',y:'46%',s:'220px',h:34, dur:'18s',delay:'-14s',dx:'16px',dy:'-14px'},
  {x:'10%',y:'74%',s:'280px',h:252,dur:'15s',delay:'-7s',dx:'20px',dy:'-18px'},
  {x:'48%',y:'68%',s:'250px',h:198,dur:'14s',delay:'-1s',dx:'-16px',dy:'-14px'},
  {x:'82%',y:'78%',s:'300px',h:164,dur:'16s',delay:'-10s',dx:'-18px',dy:'-16px'},
  {x:'32%',y:'88%',s:'200px',h:12, dur:'13s',delay:'-6s',dx:'14px',dy:'-20px'},
  {x:'62%',y:'90%',s:'190px',h:290,dur:'17s',delay:'-12s',dx:'-12px',dy:'-18px'},
  {x:'88%',y:'10%',s:'170px',h:44, dur:'14s',delay:'-8s',dx:'-14px',dy:'14px'},
 ];
 host.innerHTML=orbs.map(o=>`<span class="bubbles-orb" style="--bx:${o.x};--by:${o.y};--bs:${o.s};--bh:${o.h};--bdur:${o.dur};--bdelay:${o.delay};--bdx:${o.dx};--bdy:${o.dy}"></span>`).join('');
 document.body.prepend(host);
 const syncVis=()=>document.documentElement.classList.toggle('bubbles-hidden',document.visibilityState==='hidden');
 document.addEventListener('visibilitychange',syncVis);
 syncVis();
})();
