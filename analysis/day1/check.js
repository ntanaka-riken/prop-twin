const MEAS={audio:[[3.7,318.4],[3.75,319.1],[3.8,319.6],[3.85,320.1],[3.9,320.7],[3.95,321.2],[4.0,321.3],[4.05,321.6],[4.1,321.7],[4.15,321.8],[4.2,322.0],[4.25,322.0],[4.3,322.1],[4.35,322.1],[4.4,322.1],[4.45,322.1],[4.5,322.1],[4.55,322.1],[4.6,322.1],[4.65,322.2],[4.7,322.3],[4.75,322.5],[4.8,322.5]],video:[[5.45,22.5],[5.483,14.1],[5.517,8.9],[5.55,2.1]]};
MEAS.low=[[11.13,162.2],[11.147,158.1],[11.163,156.0],[11.18,148.6],[11.197,146.5],[11.213,141.3],[11.23,138.2],[11.247,132.9],[11.263,128.7],[11.28,125.6],[11.297,122.5],[11.313,117.2],[11.33,114.1],[11.347,109.9],[11.363,106.8],[11.38,101.5],[11.397,99.4],[11.413,94.2],[11.43,90.0],[11.447,89.0],[11.463,84.8],[11.48,77.5],[11.497,77.5],[11.514,71.2],[11.53,71.2],[11.547,53.4],[11.564,54.4],[11.58,47.1],[11.597,46.1],[11.614,42.9],[11.63,40.8],[11.647,37.7],[11.664,35.6],[11.68,28.3],[11.697,28.3],[11.714,26.2],[11.73,24.1],[11.747,18.8],[11.764,16.7],[11.78,15.7],[11.797,12.6],[11.814,13.6],[11.83,11.5],[11.847,8.4]];
MEAS.full2=[[8.87,316.0],[10.85,319.3]];
const ID={Vs:4.9,V0:1.3,rd:0.6,R:5.43,L:0.001882,f_pwm:1000,Vf:1.0,K:0.002,J:1e-6,Tc:0.00026,Ts:0.0003188,b:0,c:6.939e-9};
const META=[
 ["J","慣性モーメント","kg·m²","prior",2e-7,4e-6,"log"],
 ["K","トルク/逆起電力定数","N·m/A","prior",8e-4,5e-3,"log"],
 ["R","巻線抵抗","Ω","fit",0.5,10,"lin"],
 ["L","巻線インダクタンス","H","fit",1e-4,1e-2,"log"],
 ["Tc","動摩擦トルク","N·m","fit",2e-5,2e-3,"log"],
 ["Ts","起動トルク(静止摩擦)","N·m","fit",1e-4,4e-3,"log"],
 ["c","空力係数 c·ω²","N·m·s²","fit",1e-9,1e-7,"log"],
 ["Vs","電源電圧","V","prior",3,6,"lin"],
 ["V0","L293D 降下(0 A)","V","prior",0.5,2.5,"lin"],
 ["rd","L293D 降下の傾き","Ω","prior",0,2,"lin"],
];
let P={...ID};

// ---- firmware: behavioural copy of blink_ota_esp8266_v36.ino dcm:* ----
class FW{
  constructor(){this.duty=0;this.dir=1;this.on=false;this.brake=false;this.ramp=null;this.step=null}
  off(){this.on=this.brake=false;this.ramp=this.step=null;this.duty=0}
  cmd(line,ms){
    const p=line.trim().split(/\s+/), n=x=>parseInt(x,10), cl=(x,a,b)=>Math.max(a,Math.min(b,x));
    if(line==="stat")return `STAT blink_ota_esp8266 v36 serial-only (L293D) [twin] duty=${this.duty} on=${this.on}`;
    if(line==="dcm:off"){this.off();return "ACK dcm:off"}
    if(line==="dcm:brake"){this.ramp=this.step=null;this.on=true;this.brake=true;this.duty=0;return "ACK dcm:brake"}
    if(p[0]==="dcm:speed"&&p.length===2&&!isNaN(n(p[1]))){const v=n(p[1]);this.ramp=this.step=null;
      if(v===0)this.off();else{this.dir=v>0?1:-1;this.duty=Math.min(Math.abs(v),255);this.on=true;this.brake=false}
      return `ACK dcm:speed dir=${this.dir} duty=${this.duty}`}
    if(p[0]==="dcm:ramp"){ if(p.length!==3||isNaN(n(p[1]))||isNaN(n(p[2])))return "ERR dcm:ramp usage: <target%> <ms>";
      const pct=cl(n(p[1]),0,100),d=cl(n(p[2]),0,30000);this.step=null;
      this.ramp={from:this.duty,to:Math.floor(pct*255/100),ms:d,st:ms};this.on=true;this.brake=false;
      return `ACK dcm:ramp ${pct}% over ${d}ms (duty ${this.ramp.from}->${this.ramp.to})`}
    if(p[0]==="dcm:ramp-step"){ if(p.length!==4||p.slice(1).some(x=>isNaN(n(x))))return "ERR dcm:ramp-step usage: <target%> <interval_ms> <inc%>";
      const pct=cl(n(p[1]),0,100),iv=cl(n(p[2]),50,10000),inc=cl(n(p[3]),1,51);this.ramp=null;
      this.step={tgt:Math.floor(pct*255/100),inc:Math.max(1,Math.floor(inc*255/100)),iv,last:ms};this.on=true;this.brake=false;
      return `ACK dcm:ramp-step target=${pct}% every=${iv}ms inc=${inc}% (duty ${this.duty}->${this.step.tgt})`}
    if(p[0]==="dcm:auto")return `ACK dcm:auto boot-soft-start=${n(p[1])?"ON":"OFF"}`;
    return `ERR unknown cmd '${line}' (stat|dcm:*)`;
  }
  tick(ms){
    if(this.ramp){const r=this.ramp,el=ms-r.st;
      if(el>=r.ms){this.duty=r.to;this.ramp=null}else if(r.ms>0)this.duty=r.from+Math.trunc((r.to-r.from)*el/r.ms)}
    if(this.step&&ms-this.step.last>=this.step.iv){const s=this.step;s.last=ms;
      this.duty=this.duty<s.tgt?Math.min(this.duty+s.inc,s.tgt):Math.max(this.duty-s.inc,s.tgt);
      if(this.duty===s.tgt)this.step=null}
  }
  bridge(){return !this.on?["coast",0]:this.brake?["brake",0]:["drive",this.dir*this.duty/255]}
}
// ---- plant: L293D + motor + propeller (same equations as motor_twin.py) ----
const S={t:0,i:0,ie:0,w:0,th:0,v:0,mode:"coast",d:0,tm:0,tl:0};
let fw=new FW(), nextTick=0, queue=[], hist=[], overlay=null;
// exponential segment i(t)=a+(i0-a)e^(-t/tau): [i(t), integral]
function seg(i0,a,tau,t){const e=Math.exp(-t/tau);return [a+(i0-a)*e,a*t+(i0-a)*tau*(1-e)]}
// one PWM period, solved exactly (speed frozen): on = Vs-V0 across R+rd, off = fast decay via clamp diodes
function drivePeriod(d,T){
  const s=d>=0?1:-1, dd=Math.abs(d), w=s*S.w; let i=s*S.ie, q=0;
  const ton=dd*T, toff=T-ton;
  if(ton>0){const Ron=P.R+P.rd; const r=seg(i,(P.Vs-P.V0-P.K*w)/Ron,P.L/Ron,ton); i=r[0]; q+=r[1]}
  if(toff>0&&i>0){const a=-(P.Vs+2*P.Vf+P.K*w)/P.R, tau=P.L/P.R, tz=tau*Math.log(1+i/-a), t=Math.min(tz,toff);
    const r=seg(i,a,tau,t); i=t<toff?0:r[0]; q+=r[1]}
  else if(toff>0&&i<0)i=0;
  S.ie=s*i; S.i=s*q/T; return s*dd*(P.Vs-P.V0);
}
function plantStep(dt){
  const [mode,d]=fw.bridge(); S.mode=mode; S.d=d; let v=0;
  if(mode==="coast"){S.i=S.ie=0}
  else if(mode==="drive"){v=drivePeriod(d,dt)}
  else{const Rt=P.R+P.rd; let q=0; for(let k=0;k<10;k++){const r=seg(S.ie,-P.K*S.w/Rt,P.L/Rt,dt/10);S.ie=r[0];q+=r[1]} S.i=q/dt}
  S.v=v; const Tm=P.K*S.i; S.tm=Tm; const w=S.w; let acc=0;
  if(w===0&&Math.abs(Tm)<=P.Ts){acc=0;S.tl=Tm}
  else{const sg=Math.sign(w!==0?w:Tm); const Tl=P.Tc*sg+P.b*w+P.c*w*Math.abs(w); S.tl=Tl; acc=(Tm-Tl)/P.J}
  let nw=w+acc*dt; if(w!==0&&nw*w<0&&Math.abs(Tm)<=P.Ts)nw=0;
  S.w=nw; S.th+=nw*dt; S.t+=dt;
}
const DT=1e-3;   // one 1 kHz PWM period
let carry=0;
function advance(sec){
  carry+=sec; const n=Math.floor(carry/DT); carry-=n*DT;
  for(let k=0;k<n;k++){
    const ms=Math.floor(S.t*1000+1e-9);
    while(queue.length&&queue[0][0]<=S.t+1e-12){const [,c]=queue.shift(); send(c,true)}
    if(S.t>=nextTick-1e-12){fw.tick(ms);nextTick+=0.005}
    plantStep(DT);
    if(Math.round(S.t*1000)%5===0)hist.push([S.t,S.w,S.i,fw.on&&!fw.brake?fw.duty*fw.dir:0]);
  }
  const cut=S.t-10.5; while(hist.length&&hist[0][0]<cut)hist.shift();
}
// ---- console ----
const logEl=document.getElementById("log");
function log(msg,cls){const d=document.createElement("div");d.textContent=msg;if(cls)d.className=cls;logEl.appendChild(d);logEl.scrollTop=logEl.scrollHeight;
  while(logEl.childNodes.length>200)logEl.removeChild(logEl.firstChild)}
function send(c,fromQueue){
  const r=fw.cmd(c,Math.floor(S.t*1000)); log(`${S.t.toFixed(3)}s >>> ${c}`); log(r,r.startsWith("ERR")?"err":"");
  if(port&&!fromQueue)serialWrite(c);
}
function resetSim(){fw=new FW();Object.assign(S,{t:0,i:0,ie:0,w:0,th:0,v:0});nextTick=0;carry=0;queue=[];hist=[];overlay=null;logEl.textContent=""}
document.getElementById("cform").addEventListener("submit",e=>{e.preventDefault();const c=document.getElementById("cmd").value.trim();if(c){overlay=null;send(c)}});
document.querySelectorAll("[data-cmd]").forEach(b=>b.addEventListener("click",()=>{overlay=null;send(b.dataset.cmd)}));
const PRESETS={
  img:[[2.817,"dcm:speed 255"],[4.817,"dcm:off"]],
  low:[[7.870,"dcm:speed 255"],[10.888,"dcm:speed 51"],[18.842,"dcm:off"]],
  fastslow:[[0.3,"dcm:speed 255"],[3.3,"dcm:speed 153"],[13.3,"dcm:off"]],
  cold:[[0.3,"dcm:speed 114"],[3.3,"dcm:off"],[4.5,"dcm:speed 127"],[7.5,"dcm:off"]],
};
const OVERLAYS={img:MEAS.audio.concat(MEAS.video),low:MEAS.full2.concat(MEAS.low)};
document.querySelectorAll("[data-preset]").forEach(b=>b.addEventListener("click",()=>{
  resetSim(); queue=PRESETS[b.dataset.preset].map(x=>x.slice()); overlay=OVERLAYS[b.dataset.preset]||null;
  log(`# preset: ${b.textContent}`);
}));
document.getElementById("reset").addEventListener("click",resetSim);
// ---- optional: mirror commands to the real board (works when opened locally in Chrome) ----
let port=null, writer=null;
const sbtn=document.getElementById("serialBtn"), sstate=document.getElementById("serialState");
if("serial" in navigator){sbtn.hidden=false;
  sbtn.addEventListener("click",async()=>{
    try{port=await navigator.serial.requestPort();await port.open({baudRate:115200});
      writer=port.writable.getWriter();sstate.textContent="実機接続中: 送信コマンドを実機にも送ります";readLoop()}
    catch(e){port=null;sstate.textContent="接続できませんでした("+e.message+")。ファイルをローカルの Chrome で開いてください。"}
  })}
async function serialWrite(c){try{await writer.write(new TextEncoder().encode(c+"\n"))}catch(e){log("serial write failed: "+e.message,"err")}}
async function readLoop(){const rd=port.readable.pipeThrough(new TextDecoderStream()).getReader();let buf="";
  for(;;){const {value,done}=await rd.read();if(done)break;buf+=value;let k;
    while((k=buf.indexOf("\n"))>=0){const line=buf.slice(0,k).trim();buf=buf.slice(k+1);if(line&&!line.startsWith("[HB]"))log("board: "+line,"rx")}}}
// ---- parameters UI ----
const pEl=document.getElementById("params");
function fmt(v){return Math.abs(v)>=0.01&&Math.abs(v)<1000?v.toPrecision(3):v.toExponential(2)}
function buildParams(){pEl.textContent="";
  for(const [k,name,unit,src,lo,hi,sc] of META){
    const d=document.createElement("div");d.className="p";
    const toS=v=>sc==="log"?(Math.log(v/lo)/Math.log(hi/lo))*1000:(v-lo)/(hi-lo)*1000;
    const fromS=s=>sc==="log"?lo*Math.pow(hi/lo,s/1000):lo+(hi-lo)*s/1000;
    d.innerHTML=`<label for="p_${k}"><span>${name} <span class="mono">${k}</span> <span class="chip ${src}">${src==="fit"?"同定":"事前"}</span></span><span class="mono" id="pv_${k}">${fmt(P[k])} ${unit}</span></label><input type="range" id="p_${k}" min="0" max="1000" value="${toS(P[k])}">`;
    d.querySelector("input").addEventListener("input",e=>{P[k]=fromS(+e.target.value);document.getElementById("pv_"+k).textContent=fmt(P[k])+" "+unit});
    pEl.appendChild(d)}}
buildParams();
document.getElementById("preset").addEventListener("click",()=>{P={...ID};buildParams()});
// ---- drawing ----
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const pc=document.getElementById("prop"), px=pc.getContext("2d");
let lastTh=0;
function drawProp(){
  const W=pc.width,c=W/2,R=W*0.44; px.clearRect(0,0,W,W);
  px.fillStyle=css("--grid");px.beginPath();px.arc(c,c,R*0.36,0,7);px.fill();     // cup rim
  const exp=1/60, sweep=S.w*exp, N=Math.max(1,Math.min(48,Math.ceil(Math.abs(sweep)/0.08)));
  px.fillStyle=css("--prop");
  for(let s=0;s<N;s++){
    const a0=S.th-sweep*s/N; px.globalAlpha=Math.min(1,1.25/N);
    for(let b=0;b<3;b++){const a=a0+b*2*Math.PI/3;
      px.save();px.translate(c,c);px.rotate(a);px.beginPath();
      px.moveTo(0,-R*0.12);px.bezierCurveTo(R*0.35,-R*0.42,R*1.02,-R*0.38,R*0.98,R*0.02);
      px.bezierCurveTo(R*0.92,R*0.30,R*0.45,R*0.22,0,R*0.12);px.closePath();px.fill();px.restore()}}
  px.globalAlpha=1;px.fillStyle=css("--prop");px.beginPath();px.arc(c,c,R*0.17,0,7);px.fill();
  px.strokeStyle=css("--ink");px.globalAlpha=.25;px.lineWidth=1;px.beginPath();px.arc(c,c,R,0,7);px.stroke();px.globalAlpha=1;
  px.fillStyle=css("--muted");px.font=`22px ${css("--mono")}`;px.fillText(`${(S.w/(2*Math.PI)).toFixed(1)} rev/s`,14,W-16);
}
const sc=document.getElementById("scope"), sx=sc.getContext("2d");
function drawScope(){
  const W=sc.width,H=sc.height,L=70,Rm=60,T=16,B=36; sx.clearRect(0,0,W,H);
  const t1=Math.max(10,S.t), t0=t1-10, X=t=>L+(t-t0)/(t1-t0)*(W-L-Rm);
  const lanes=[[T,H*0.58],[H*0.58+18,H*0.79],[H*0.79+18,H-B]];
  sx.font=`20px ${css("--mono")}`; sx.lineWidth=1;
  const lane=(k,max,label,ticks)=>{const [a,b]=lanes[k];const Y=v=>b-(v/max)*(b-a);
    sx.strokeStyle=css("--grid");sx.fillStyle=css("--muted");
    for(const v of ticks){sx.beginPath();sx.moveTo(L,Y(v));sx.lineTo(W-Rm,Y(v));sx.stroke();sx.fillText(String(v),6,Y(v)+6)}
    sx.save();sx.fillStyle=css("--muted");sx.fillText(label,W-Rm+6,a+16);sx.restore();return Y};
  const Yr=lane(0,4000,"rpm",[0,1000,2000,3000,4000]);
  const Yi=lane(1,1.0,"A",[0,0.5,1]);
  const Yd=lane(2,255,"duty",[0,255]);
  sx.fillStyle=css("--muted");
  for(let t=Math.ceil(t0);t<=t1;t++){sx.fillText(t+"s",X(t)-12,H-8)}
  const line=(idx,Y,col,f=x=>x)=>{sx.strokeStyle=col;sx.lineWidth=3;sx.beginPath();let st=false;
    for(const h of hist){if(h[0]<t0)continue;const x=X(h[0]),y=Y(f(h[idx]));st?sx.lineTo(x,y):sx.moveTo(x,y);st=true}sx.stroke()};
  line(1,Yr,css("--prop"),w=>Math.abs(w)*60/(2*Math.PI));
  line(2,Yi,css("--cool"),Math.abs);
  line(3,Yd,css("--muted"),Math.abs);
  if(overlay){sx.fillStyle=css("--meas");
    for(const [t,w] of overlay){if(t<t0||t>t1)continue;sx.beginPath();sx.arc(X(t),Yr(w*60/(2*Math.PI)),5,0,7);sx.fill()}}
}
const $=id=>document.getElementById(id);
function torqueBars(){
  const items=[["モーター K·i",S.tm,"--prop"],["動摩擦 Tc",S.w!==0?P.Tc:0,"--muted"],["空力 c·ω²",P.c*S.w*S.w,"--cool"],["加速に使う分",S.tm-S.tl,"--ok"]];
  const mx=Math.max(1e-4,P.K*(P.Vs-P.V0)/(P.R+P.rd));
  $("torque").innerHTML=items.map(([n,v,c])=>`<div class="tbar"><span>${n}</span><div class="b"><i style="width:${Math.min(100,Math.abs(v)/mx*100)}%;background:var(${c})"></i></div><span class="mono">${(v*1000).toFixed(3)} mN·m</span></div>`).join("")+
   `<div class="muted" style="margin-top:4px">起動トルク Ts = ${(P.Ts*1000).toFixed(2)} mN·m(停止中はこれを超えるまで回らない)</div>`;
}
function readouts(){
  const rpm=Math.abs(S.w)*60/(2*Math.PI);
  $("clock").textContent=S.t.toFixed(3)+" s"; $("r_rpm").textContent=rpm.toFixed(0);
  $("r_i").textContent=S.i.toFixed(2); $("r_v").textContent=S.v.toFixed(2);
  $("r_d").textContent=`${fw.on&&!fw.brake?fw.duty:0}`;
  const mc=$("modechip"); mc.textContent=S.mode; mc.className="mode "+S.mode;
  $("c_vs").textContent="Vs "+P.Vs.toFixed(2);
  $("c_mode").textContent={coast:"coast (Hi-Z)",drive:fw.dir>0?"drive 正転":"drive 逆転",brake:"brake (短絡)"}[S.mode];
  const drop=S.mode==="drive"?Math.abs(S.d)*(P.V0+P.rd*Math.abs(S.i)):0;
  $("c_drop").textContent="降下 "+drop.toFixed(2)+" V"; $("c_en").textContent="EN=IO15 duty "+(fw.on&&!fw.brake?fw.duty:fw.brake?255:0);
  $("c_vm").textContent="V "+S.v.toFixed(2); $("c_i").textContent="i "+S.i.toFixed(3)+" A";
  $("c_emf").textContent="EMF "+(P.K*S.w).toFixed(2); $("c_r").textContent="R "+P.R.toFixed(2)+" Ω";
  $("c_w").textContent="ω "+S.w.toFixed(0)+" rad/s";
  $("w1").setAttribute("stroke-width",2+6*Math.min(1,Math.abs(S.i)));$("w2").setAttribute("stroke-width",2+6*Math.min(1,Math.abs(S.i)));
}
let last=performance.now();
function frame(now){
  const real=Math.min(0.05,(now-last)/1000); last=now;
  advance(real*($("slow").checked?0.25:1));
  drawProp(); drawScope(); readouts(); torqueBars();
  requestAnimationFrame(frame);
}
// open in a working state: replay the filmed run
queue=PRESETS.img.map(x=>x.slice()); overlay=OVERLAYS.img; log("# preset: 動画 IMG_5741 を再生(全速2秒)");
requestAnimationFrame(frame);
