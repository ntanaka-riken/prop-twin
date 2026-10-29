function drawScope(){
  // canvas follows its CSS box (fills the panel), drawn in CSS pixels at device resolution
  const lanes=LANES.filter(L=>laneOn[L.key]);
  const dpr=Math.min(2,window.devicePixelRatio||1), W=Math.max(280,sc.clientWidth), H=Math.max(220,sc.clientHeight);
  if(sc.width!==Math.round(W*dpr)||sc.height!==Math.round(H*dpr)){sc.width=Math.round(W*dpr);sc.height=Math.round(H*dpr)}
  sx.setTransform(dpr,0,0,dpr,0,0); sx.clearRect(0,0,W,H);
  const B=18,Lm=44,Rm=6, per=(H-B)/Math.max(1,lanes.length), fs=Math.max(9,Math.min(12,per/9));
  const t1=Math.max(10,S.t), t0=t1-10, X=t=>Lm+(t-t0)/(t1-t0)*(W-Lm-Rm);
  const vis=hist.filter(h=>h.t>=t0);
  const OV=typeof overlay!=="undefined"?overlay:null, TOV=typeof thrustOverlay!=="undefined"&&thrustOverlay;
  sx.lineWidth=1;
  lanes.forEach((L,k)=>{
    const a=k*per+fs+6, b=(k+1)*per-4;
    let lo=0,hi=0; for(const h of vis)for(const sr of L.ser){const v=sr[1](h);if(v<lo)lo=v;if(v>hi)hi=v}
    if(L.live)for(const l of live)if(l.t>=t0)hi=Math.max(hi,L.live(l));
    if(L.meas&&OV)for(const [t,w] of OV)if(t>=t0)hi=Math.max(hi,w*RPM);
    if(L.thrust&&TOV)for(const [t,g] of THRUST_MEAS)if(t>=t0)hi=Math.max(hi,g);
    if(hi-lo<1e-9){hi=lo+1}
    const st=niceStep(hi-lo); lo=Math.floor(lo/st)*st; hi=Math.ceil(hi*1.05/st)*st;
    const Y=v=>b-(v-lo)/(hi-lo)*(b-a);
    sx.font=`${fs}px ${css("--mono")}`; sx.strokeStyle=css("--grid"); sx.fillStyle=css("--muted");
    for(let v=lo;v<=hi+1e-9;v+=st){sx.beginPath();sx.moveTo(Lm,Y(v));sx.lineTo(W-Rm,Y(v));sx.stroke();
      const lab=(Math.abs(v)<1e-9?0:+v.toPrecision(3)).toString(); sx.fillText(lab,Lm-4-sx.measureText(lab).width,Y(v)+fs*0.35)}
    if(lo<0){sx.strokeStyle=css("--muted");sx.beginPath();sx.moveTo(Lm,Y(0));sx.lineTo(W-Rm,Y(0));sx.stroke()}
    for(const [nm,f,col] of L.ser){sx.strokeStyle=css(col);sx.lineWidth=1.8;sx.beginPath();let on=false;
      for(const h of vis){const x=X(h.t),y=Y(f(h));on?sx.lineTo(x,y):sx.moveTo(x,y);on=true}sx.stroke()}
    const dot=(x,y,r)=>{sx.beginPath();sx.arc(x,y,r,0,7);sx.fill()};
    if(L.meas&&OV){sx.fillStyle=css("--meas");for(const [t,w] of OV)if(t>=t0&&t<=t1)dot(X(t),Y(w*RPM),3)}
    if(L.thrust&&TOV){sx.fillStyle=css("--meas");for(const [t,g] of THRUST_MEAS)if(t>=t0&&t<=t1)dot(X(t),Y(g),3.5)}
    if(L.live&&live.length){sx.fillStyle=css("--wire");for(const l of live)if(l.t>=t0)dot(X(l.t),Y(L.live(l)),2.4)}
    // lane title + legend with latest values, on one line above the lane
    const ty=k*per+fs+1; sx.fillStyle=css("--ink"); sx.font=`bold ${fs}px ${css("--body")}`;
    const title=`${L.name} [${L.unit}]`; sx.fillText(title,Lm,ty); let x=Lm+sx.measureText(title).width+12;
    sx.font=`${fs}px ${css("--mono")}`; const lastH=vis[vis.length-1];
    for(const [nm,f,col] of L.ser){if(x>W-60)break; sx.fillStyle=css(col);sx.fillRect(x,ty-fs*0.45,10,3);sx.fillStyle=css("--muted");
      const txt=`${nm}${lastH?" "+(+f(lastH).toPrecision(3)):""}`;sx.fillText(txt,x+13,ty);x+=sx.measureText(txt).width+24}
    if(L.live&&live.length&&x<W-60){const lv=live[live.length-1];sx.fillStyle=css("--wire");dot(x+4,ty-fs*0.35,3);sx.fillStyle=css("--muted");sx.fillText(`${L.liveName} ${+L.live(lv).toPrecision(3)}`,x+11,ty)}
  });
  sx.fillStyle=css("--muted"); sx.font=`${fs}px ${css("--mono")}`;
  for(let t=Math.ceil(t0);t<=t1;t++){const s=t+"s";sx.fillText(s,X(t)-sx.measureText(s).width/2,H-4)}
}
