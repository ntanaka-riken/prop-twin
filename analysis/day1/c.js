// ===================== twin model (same equations as motor_twin.py / twin.html) =====================
const P={kT:1.70e-7,Vs:4.9,V0:2.173,rd:0.6,R:7.676,L:0.002739,f_pwm:1000,Vf:1.0,V_bk:1.164,K:0.00606,J:9.531e-7,Tc:0.0002844,Ts:0.0005008,b:3.616e-7,c:2.848e-9};
class FW{
  constructor(boot){this.duty=0;this.dir=1;this.on=false;this.brake=false;this.ramp=null;this.step=null;this.auto=!!boot;this.bootStage=0}
  off(){this.on=this.brake=false;this.ramp=this.step=null;this.duty=0}
  cmd(line,ms){
    const p=line.trim().split(/\s+/), n=x=>parseInt(x,10), cl=(x,a,b)=>Math.max(a,Math.min(b,x));
    if(line.startsWith("dcm:")&&!line.startsWith("dcm:auto "))this.bootStage=2;
    if(line==="stat")return `STAT blink_ota_esp8266 v36 [twin3d] duty=${this.duty} on=${this.on}`;
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
    if(p[0]==="dcm:auto"){this.auto=n(p[1])!==0; if(!this.auto&&this.bootStage===1){this.off();this.bootStage=2} return `ACK dcm:auto boot-soft-start=${this.auto?"ON":"OFF"}`}
    return `ERR unknown cmd '${line}' (stat|dcm:*)`;
  }
  tick(ms){
    if(this.auto&&this.bootStage===0&&ms>=5000){this.bootStage=1;this.step=null;this.dir=1;this.duty=127;
      this.ramp={from:127,to:255,ms:5000,st:ms};this.on=true;this.brake=false;log("[DCM] boot sequence: 50% -> 100% over 5s");flash()}
    if(this.bootStage===1&&ms>=11000){this.bootStage=2;this.off();log("[DCM] boot sequence done: coast")}
    if(this.ramp){const r=this.ramp,el=ms-r.st;
      if(el>=r.ms){this.duty=r.to;this.ramp=null}else if(r.ms>0)this.duty=r.from+Math.trunc((r.to-r.from)*el/r.ms)}
    if(this.step&&ms-this.step.last>=this.step.iv){const s=this.step;s.last=ms;
      this.duty=this.duty<s.tgt?Math.min(this.duty+s.inc,s.tgt):Math.max(this.duty-s.inc,s.tgt);
      if(this.duty===s.tgt)this.step=null}
  }
  bridge(){return !this.on?["coast",0]:this.brake?["brake",0]:["drive",this.dir*this.duty/255]}
}
// ---- closed-loop speed control + tachometer (same constants as the .ino and motor_twin.py) ----
const CTL={MS:50,PROBE_MS:2,KP:0.04,KI:0.25,ALPHA:0.5,RPM_MIN:750,RPM_MAX:3200,FLOOR:102,KICK:0.4,NOISE:0.20,
  FF:[[0,0],[700,102],[1227,127],[1629,153],[2169,204],[3057,255]]};
function ffDuty(r){for(let k=1;k<CTL.FF.length;k++)if(r<=CTL.FF[k][0]){const [r0,d0]=CTL.FF[k-1],[r1,d1]=CTL.FF[k];return d0+(d1-d0)*(r-r0)/(r1-r0)}return 255}
function ctlInit(f){if(f.ctl===undefined)Object.assign(f,{ctl:false,ref:0,filt:0,meas:0,I:0,ctlLast:-1e9,kickUntil:-1,probeUntil:-1,tel:false})}
const _fwCmd=FW.prototype.cmd, _fwBridge=FW.prototype.bridge;
FW.prototype.cmd=function(line,ms){
  ctlInit(this); const p=line.trim().split(/\s+/);
  if(line.startsWith("dcm:")&&!line.startsWith("dcm:auto "))this.ctl=false;
  if(p[0]==="rpm:set"&&p.length===2){const ref=parseFloat(p[1]); if(isNaN(ref))return "ERR rpm:set usage: <rpm>";
    if(this.bootStage!==undefined)this.bootStage=2;
    if(ref<=0){this.ctl=false;this.off();return "ACK rpm:set ref=0"}
    this.ref=Math.min(Math.max(ref,CTL.RPM_MIN),CTL.RPM_MAX);
    if(!this.ctl){this.I=0;this.filt=this.meas=Math.abs(S.w)*30/Math.PI}
    this.ctl=true;this.ramp=this.step=null;this.on=true;this.brake=false;this.dir=1;
    if(this.filt<300){this.kickUntil=ms+300;this.duty=255}
    return `ACK rpm:set ref=${Math.round(this.ref)}`}
  if(line==="rpm:off"){this.ctl=false;this.off();return "ACK rpm:off"}
  if(line==="tel:on"){this.tel=true;return "ACK tel:on period_ms=50"}
  if(line==="tel:off"){this.tel=false;return "ACK tel:off"}
  return _fwCmd.call(this,line,ms);
};
// every CTL.MS: EN low PROBE_MS (tachometer), EMA, feedforward + PI, 40 % floor
FW.prototype.control=function(ms){
  ctlInit(this); if(!(this.ctl||this.tel)||ms-this.ctlLast<CTL.MS)return;
  this.ctlLast=ms; this.probeUntil=ms+CTL.PROBE_MS;
  this.meas=Math.abs(S.w)*30/Math.PI*(1+CTL.NOISE*(2*Math.random()-1));
  this.filt+=CTL.ALPHA*(this.meas-this.filt);
  if(this.ctl){
    if(ms<this.kickUntil&&this.filt<CTL.KICK*this.ref)this.duty=255;
    else{const e=this.ref-this.filt, ff=ffDuty(this.ref), u=ff+CTL.KP*e+this.I;
      if((u>CTL.FLOOR&&u<255)||(u>=255&&e<0)||(u<=CTL.FLOOR&&e>0))this.I+=CTL.KI*e*CTL.MS/1000;
      this.duty=Math.trunc(Math.min(Math.max(ff+CTL.KP*e+this.I,CTL.FLOOR),255))}
    this.on=true;this.brake=false;this.dir=1}
};
FW.prototype.bridge=function(){ctlInit(this);return S.t*1000<this.probeUntil?["coast",0]:_fwBridge.call(this)};
// ---- live telemetry from the board (TEL lines over Web Serial), stamped with twin time ----
const live=[];
function onBoardLine(line){
  if(!line.startsWith("TEL"))return false;
  const m=Object.fromEntries(line.split(/\s+/).slice(1).map(x=>x.split("=")));
  live.push({t:S.t,rpm:+m.rpm,filt:+m.filt,duty:+m.duty,ref:+m.ref});
  while(live.length&&live[0].t<S.t-10.5)live.shift();
  return true;
}
const liveThrust=r=>P.kT*(r*Math.PI/30)**2/9.80665*1000;
const S={t:0,i:0,ie:0,isq:0,w:0,th:0,v:0,vt:0,mode:"coast",d:0,tm:0,tl:0,acc:0,
  Psup:0,Pcu:0,Pdrv:0,Pdio:0,Pem:0,Pfr:0,Pair:0};
let fw=new FW(false), nextTick=0, queue=[], carry=0, ledUntil=-1, hist=[];
// exponential segment i(t)=a+(i0-a)e^(-t/tau): [i(t), ∫i dt, ∫i^2 dt]
function seg(i0,a,tau,t){const e=Math.exp(-t/tau), d=i0-a;
  return [a+d*e, a*t+d*tau*(1-e), a*a*t+2*a*d*tau*(1-e)+d*d*tau/2*(1-e*e)]}
function drivePeriod(d,T){
  const s=d>=0?1:-1, dd=Math.abs(d), w=s*S.w, emf=P.K*w; let i=s*S.ie;
  const ton=dd*T, toff=T-ton; let q=0,q2=0,qon=0,q2on=0,qoff=0,tcond=0;
  if(ton>0){const Ron=P.R+P.rd; const r=seg(i,(P.Vs-P.V0-emf)/Ron,P.L/Ron,ton); i=r[0]; qon=r[1]; q2on=r[2]}
  if(toff>0&&i>0){const a=-(P.Vs+2*P.Vf+emf)/P.R, tau=P.L/P.R, tz=tau*Math.log(1+i/-a), t=Math.min(tz,toff);
    const r=seg(i,a,tau,t); i=t<toff?0:r[0]; qoff=r[1]; q2+=r[2]; tcond=t}
  else if(toff>0&&i<0)i=0;
  q=qon+qoff; q2+=q2on;
  S.ie=s*i; S.i=s*q/T; S.isq=q2/T;
  // terminal voltage: on = Vs-V0-rd*i, off while conducting = -(Vs+2Vf), off and open = back-EMF
  S.vt=s*((P.Vs-P.V0)*ton-P.rd*qon-(P.Vs+2*P.Vf)*tcond+emf*(toff-tcond))/T;
  S.Psup=(P.Vs*qon-P.Vs*qoff)/T;                       // fast decay returns energy to VCC2
  S.Pdrv=(P.V0*qon+P.rd*q2on)/T; S.Pdio=2*P.Vf*qoff/T;
  return s*dd*(P.Vs-P.V0);
}
function plantStep(dt){
  const [mode,d]=fw.bridge(); S.mode=mode; S.d=d; let v=0;
  S.Psup=S.Pdrv=S.Pdio=0;
  if(mode==="coast"){S.i=S.ie=S.isq=0; S.vt=P.K*S.w}
  else if(mode==="drive"){v=drivePeriod(d,dt)}
  else{const s=S.w>=0?1:-1, emf=P.K*Math.abs(S.w), a=emf>P.V_bk?-(emf-P.V_bk)/P.R:0; // brake: high side + clamp diode loop
    const r=seg(s*S.ie,a,P.L/P.R,dt); S.ie=s*Math.min(r[0],0); S.i=s*Math.min(r[1]/dt,0); S.isq=a<0?r[2]/dt:0;
    S.Pdio=P.V_bk*Math.abs(S.i); S.vt=a<0?s*P.V_bk:P.K*S.w}
  S.v=v; S.Pcu=P.R*S.isq; S.Pem=P.K*S.i*S.w;
  const Tm=P.K*S.i; S.tm=Tm; const w=S.w; let acc=0;
  if(w===0&&Math.abs(Tm)<=P.Ts){acc=0;S.tl=Tm}
  else{const sg=Math.sign(w!==0?w:Tm); const Tl=P.Tc*sg+P.b*w+P.c*w*Math.abs(w); S.tl=Tl; acc=(Tm-Tl)/P.J}
  let nw=w+acc*dt; if(w!==0&&nw*w<0&&Math.abs(Tm)<=P.Ts)nw=0;
  S.acc=(nw-w)/dt; S.Pfr=(w!==0?P.Tc:0)*Math.abs(w)+P.b*w*w; S.Pair=P.c*Math.abs(w)**3;
  S.w=nw; S.th+=nw*dt; S.t+=dt;
}
function advance(sec){
  carry+=sec; const n=Math.floor(carry/1e-3); carry-=n*1e-3;
  for(let k=0;k<n;k++){
    while(queue.length&&queue[0][0]<=S.t+1e-12){send(queue.shift()[1])}
    if(S.t>=nextTick-1e-12){fw.tick(Math.floor(S.t*1000+1e-9));nextTick+=0.005}
    fw.control(Math.floor(S.t*1000+1e-9));
    plantStep(1e-3);
    if(Math.round(S.t*1000)%5===0)hist.push({t:S.t,w:S.w,duty:fw.on&&!fw.brake?fw.duty*fw.dir:0,vt:S.vt,emf:P.K*S.w,
      i:S.i,irms:Math.sqrt(S.isq),Tm:S.tm,Tfr:S.w!==0?P.Tc*Math.sign(S.w):0,Tair:P.c*S.w*Math.abs(S.w),Tacc:P.J*S.acc,
      Psup:S.Psup,Pem:S.Pem,Pcu:S.Pcu,Pdrv:S.Pdrv+S.Pdio,Pfr:S.Pfr,Pair:S.Pair,thr:P.kT*S.w*S.w/9.80665*1000,ref:fw.ctl?fw.ref:0});
  }
  const cut=S.t-10.5; while(hist.length&&hist[0].t<cut)hist.shift();
}
const logEl=document.getElementById("log");
function log(m,c){const d=document.createElement("div");d.textContent=m;if(c)d.className=c;logEl.appendChild(d);logEl.scrollTop=logEl.scrollHeight;while(logEl.childNodes.length>200)logEl.removeChild(logEl.firstChild)}
function flash(){ledUntil=S.t+0.1}
function send(c){const r=fw.cmd(c,Math.floor(S.t*1000));log(`${S.t.toFixed(3)}s >>> ${c}`);log(r,r.startsWith("ERR")?"err":"");if(r.startsWith("ACK dcm:")||r.startsWith("ACK rpm:"))flash();if(port)serialWrite(c)}
// ---- optional: mirror commands to the real board (Chrome, page served from localhost) ----
let port=null, writer=null;
async function serialWrite(c){try{await writer.write(new TextEncoder().encode(c+"\n"))}catch(e){log("serial write failed: "+e.message,"err")}}
async function readLoop(){const rd=port.readable.pipeThrough(new TextDecoderStream()).getReader();let buf="";
  for(;;){const {value,done}=await rd.read();if(done)break;buf+=value;let k;
    while((k=buf.indexOf("\n"))>=0){const line=buf.slice(0,k).trim();buf=buf.slice(k+1);if(line&&!line.startsWith("[HB]")&&!onBoardLine(line))log("board: "+line)}}}
if("serial" in navigator){const b=document.getElementById("serialBtn");b.hidden=false;
  b.addEventListener("click",async()=>{const st=document.getElementById("serialState");
    try{port=await navigator.serial.requestPort();await port.open({baudRate:115200});writer=port.writable.getWriter();
      st.textContent="実機接続中: コマンドを実機にも送り、TEL を重ねて表示します";readLoop();
      document.getElementById("slow").checked=false; serialWrite("dcm:auto 0"); serialWrite("tel:on"); fw.cmd("tel:on",Math.floor(S.t*1000))}
    catch(e){port=null;st.textContent="接続できませんでした("+e.message+")。ローカルの Chrome で開いてください。"}})}
function resetSim(boot){live.length=0;fw=new FW(boot);Object.assign(S,{t:0,i:0,ie:0,isq:0,w:0,th:S.th,vt:0,acc:0});nextTick=0;carry=0;queue=[];hist=[];logEl.textContent=""}
const PRESETS={
  boot:{boot:true,q:[]},
  img:{q:[[2.817,"dcm:speed 255"],[4.817,"dcm:off"]]},
  low:{q:[[0.5,"dcm:speed 255"],[3.5,"dcm:speed 51"],[11.5,"dcm:off"]]},
  rpmctl:{q:[[0,"tel:on"],[0.2,"rpm:set 1500"],[3,"rpm:set 2500"],[6,"rpm:set 1000"],[9,"rpm:set 2000"],[12,"rpm:off"]]},
  brake:{q:[[0.5,"dcm:speed 255"],[3.5,"dcm:off"],[6,"dcm:speed 255"],[9,"dcm:brake"],[11,"dcm:off"]]},
};
document.querySelectorAll("[data-preset]").forEach(b=>b.addEventListener("click",()=>{const p=PRESETS[b.dataset.preset];resetSim(!!p.boot);queue=p.q.map(x=>x.slice());log("# "+b.textContent)}));
document.querySelectorAll("[data-cmd]").forEach(b=>b.addEventListener("click",()=>send(b.dataset.cmd)));
document.getElementById("cform").addEventListener("submit",e=>{e.preventDefault();const c=document.getElementById("cmd").value.trim();if(c)send(c)});
document.getElementById("reset").addEventListener("click",()=>resetSim(false));

// ===================== propeller geometry (mm) =====================
// half-chord / R vs r / R, measured on the flat photo (propeller on the balance, 2.0 g)
const CHORD=[[0.34,0.25],[0.40,0.311],[0.45,0.359],[0.50,0.396],[0.55,0.417],[0.60,0.442],[0.65,0.459],[0.70,0.46],[0.75,0.461],[0.80,0.454],[0.85,0.433],[0.90,0.381],[0.95,0.235],[1.0,0]];
const GEO={R:32,hubR:0.345*32,rootR:0.31*32,blades:3, cupTop:91.6};
function halfWidth(r){ // measured outline (CHORD table), scaled by the current radius
  const x=r/GEO.R; if(x<=CHORD[0][0])return CHORD[0][1]*GEO.R; if(x>=1)return 0;
  for(let k=1;k<CHORD.length;k++)if(x<=CHORD[k][0]){const [a,ya]=CHORD[k-1],[b,yb]=CHORD[k];return (ya+(yb-ya)*(x-a)/(b-a))*GEO.R}
  return 0;
}
function sweep(r){return 0.12*(r-GEO.rootR)}                 // leading edge swept back (mm)
function pitch(r){return (24-10*(r-GEO.rootR)/(GEO.R-GEO.rootR))*Math.PI/180}
function bladeArea(){let A=0,Ir=0;const dr=0.05;for(let r=GEO.rootR;r<GEO.R;r+=dr){const w=2*halfWidth(r)/Math.cos(pitch(r));A+=w*dr;Ir+=w*dr*r*r}return {A,Ir}}
function jFromMass(mg){ // mass in g -> J in kg m^2 ; uniform areal density over 3 blades + hemispherical hub shell
  const {A,Ir}=bladeArea(); const Ah=2*Math.PI*GEO.hubR**2; const Atot=GEO.blades*A+Ah;
  const sigma=mg/Atot; // g/mm^2
  const Jbl=GEO.blades*sigma*Ir, Jhub=sigma*Ah*(2/3)*GEO.hubR**2; // g mm^2
  return {J:(Jbl+Jhub)*1e-9, Jbl:Jbl*1e-9, Jhub:Jhub*1e-9, Atot, A};
}
function updateJ(){
  const m=parseFloat(document.getElementById("m_prop").value), D=parseFloat(document.getElementById("d_prop").value), jr=parseFloat(document.getElementById("j_rotor").value)||0;
  if(D>20){GEO.R=D/2; GEO.hubR=0.345*GEO.R; GEO.rootR=0.31*GEO.R; rebuildRotor&&rebuildRotor()}
  const el=document.getElementById("jres");
  if(!(m>0)){el.textContent="質量を入れてください。ツインの現在値 J = 9.5e-7 kg·m²";return}
  const r=jFromMass(m), Jt=r.J+jr;
  el.innerHTML=`羽根 ${r.Jbl.toExponential(2)} + ハブ ${r.Jhub.toExponential(2)} + 回転子 ${jr.toExponential(1)}<br>`+
    `<b>J = ${Jt.toExponential(2)} kg·m²</b>(ツインの現在値 9.5e-7 の ${(Jt/9.531e-7).toFixed(2)} 倍)<br>`+
    `<span class="muted">羽根1枚の投影面積 ${r.A.toFixed(0)} mm²、全体 ${r.Atot.toFixed(0)} mm²</span>`;
}
["m_prop","d_prop","j_rotor"].forEach(id=>document.getElementById(id).addEventListener("input",updateJ));

// ===================== three.js scene =====================
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const canvas=document.getElementById("view"), stage=document.getElementById("stage");
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:true});
renderer.setPixelRatio(Math.min(2,window.devicePixelRatio||1));
renderer.outputEncoding=THREE.sRGBEncoding;
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(35,16/9,5,5000);
const controls=new THREE.OrbitControls(camera,canvas); controls.enableDamping=true; controls.target.set(20,60,20);
function view(name){
  const v={side:[[-210,190,250],[20,55,25]],top:[[5,420,6],[20,40,25]],close:[[-105,175,125],[0,92,0]]}[name];
  camera.position.set(...v[0]); controls.target.set(...v[1]); controls.update();
}
view("side");
["side","top","close"].forEach(n=>document.getElementById("v_"+n).addEventListener("click",()=>view(n)));
scene.add(new THREE.HemisphereLight(0xffffff,0x8a8070,0.95));
const sun=new THREE.DirectionalLight(0xffffff,0.55); sun.position.set(-150,300,120); scene.add(sun);

// scanned bench
fetch("3d/rig_mesh.json").then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}).then(j=>{
  const bin=atob(j.b64), u8=new Uint8Array(bin.length); for(let k=0;k<bin.length;k++)u8[k]=bin.charCodeAt(k); const buf=u8.buffer;
  const hd=new Int32Array(buf,0,2), nv=hd[0], ni=hd[1];
  const pos=new Float32Array(buf,8,nv*3), uv=new Float32Array(buf,8+nv*12,nv*2), idx=new Uint32Array(buf,8+nv*20,ni);
  const g=new THREE.BufferGeometry(); g.setAttribute("position",new THREE.BufferAttribute(pos,3)); g.setAttribute("uv",new THREE.BufferAttribute(uv,2));
  g.setIndex(new THREE.BufferAttribute(idx,1)); g.computeVertexNormals();
  const tex=new THREE.TextureLoader().load("3d/rig_tex.jpg"); tex.encoding=THREE.sRGBEncoding; tex.anisotropy=4;
  scene.add(new THREE.Mesh(g,new THREE.MeshLambertMaterial({map:tex,side:THREE.DoubleSide})));
  document.getElementById("loading").hidden=true;
  document.getElementById("meshinfo").textContent=`${nv.toLocaleString()} 頂点 / ${(ni/3).toLocaleString()} 三角形`;
}).catch(e=>{document.getElementById("loading").textContent="スキャンを読み込めませんでした("+e.message+")。ファイルを HTTP で配信して開いてください。"});

// motor + holder (130-class can: Ø20.4 x 25 mm, flats 15 mm) — sits in the cup top
const rig=new THREE.Group(); scene.add(rig);
const metal=new THREE.MeshStandardMaterial({color:0xb9bdbd,metalness:0.8,roughness:0.35});
const can=new THREE.Mesh(new THREE.CylinderGeometry(10.2,10.2,14,40),metal); can.position.y=GEO.cupTop+2; rig.add(can);
const cap=new THREE.Mesh(new THREE.CylinderGeometry(5,6.5,2.5,32),new THREE.MeshStandardMaterial({color:0xe9e4d6,roughness:0.8})); cap.position.y=GEO.cupTop+10.2; rig.add(cap);
const shaft=new THREE.Mesh(new THREE.CylinderGeometry(1,1,6,12),metal); shaft.position.y=GEO.cupTop+13.5; rig.add(shaft);
// rotor: hub + 3 blades, rebuilt when the diameter changes
const rotor=new THREE.Group(); rotor.position.y=GEO.cupTop+14; rig.add(rotor);
const ghosts=[]; const NG=10;
const bladeMat=()=>new THREE.MeshStandardMaterial({color:new THREE.Color(css("--prop")||"#e2b400"),roughness:0.35,metalness:0,side:THREE.DoubleSide,transparent:true,opacity:1,depthWrite:true});
function bladeGeometry(){
  const NR=40, NC=14, verts=[], ids=[];
  for(let a=0;a<=NR;a++){const r=GEO.rootR+(GEO.R-GEO.rootR)*a/NR, hw=Math.max(0.3,halfWidth(r)), ph=pitch(r), sw=sweep(r);
    for(let b=0;b<=NC;b++){const t=-1+2*b/NC, c=t*hw-sw, cup=-0.06*hw*(1-t*t);
      verts.push(r, c*Math.sin(ph)+cup, c*Math.cos(ph))}}
  for(let a=0;a<NR;a++)for(let b=0;b<NC;b++){const i=a*(NC+1)+b;ids.push(i,i+1,i+NC+1,i+1,i+NC+2,i+NC+1)}
  const g=new THREE.BufferGeometry(); g.setAttribute("position",new THREE.Float32BufferAttribute(verts,3)); g.setIndex(ids); g.computeVertexNormals(); return g;
}
function makeRotor(mat){
  const grp=new THREE.Group(), bg=bladeGeometry();
  for(let k=0;k<GEO.blades;k++){const m=new THREE.Mesh(bg,mat);m.rotation.y=k*2*Math.PI/GEO.blades;grp.add(m)}
  return grp;
}
const hubMat=new THREE.MeshStandardMaterial({color:0xf2a81d,roughness:0.3});
const hub=new THREE.Mesh(new THREE.SphereGeometry(GEO.hubR,40,20,0,2*Math.PI,0,Math.PI/2),hubMat); hub.position.y=-1; rotor.add(hub);
const hubBase=new THREE.Mesh(new THREE.CylinderGeometry(GEO.hubR,GEO.hubR,3,40),hubMat); hubBase.position.y=-2.5; rotor.add(hubBase);
let rebuildRotor=function(){
  ghosts.forEach(g=>{rotor.remove(g);g.children.forEach(c=>c.geometry.dispose())}); ghosts.length=0;
  for(let k=0;k<NG;k++){const g=makeRotor(bladeMat());rotor.add(g);ghosts.push(g)}
};
rebuildRotor();
// propeller on/off (the tape flag replaces it in the propeller-off runs)
const J_ROTOR=2.651e-7, ROT={prop:{J:P.J,c:P.c,kT:P.kT},bare:{J:J_ROTOR,c:0,kT:0}};
const flag=new THREE.Mesh(new THREE.BoxGeometry(46,0.3,6),new THREE.MeshStandardMaterial({color:0xe8dc9a,roughness:0.8,side:THREE.DoubleSide}));
flag.visible=false; rotor.add(flag);
let rotorKind="prop";
function setRotor(k){rotorKind=k;P.J=ROT[k].J;P.c=ROT[k].c;P.kT=ROT[k].kT;const bare=k==="bare";
  hub.visible=hubBase.visible=!bare; flag.visible=bare; ghosts.forEach(g=>g.children.forEach(m=>m.visible=!bare))}
document.getElementById("rot_prop").addEventListener("change",()=>setRotor("prop"));
document.getElementById("rot_bare").addEventListener("change",()=>setRotor("bare"));
// sync LED (IO14) on the cup wall, toward the breadboard side
const ledAz=Math.atan2(54.7,44.3)-0.9, ledH=72, ledR=37.8-0.142*ledH+3;
const ledMat=new THREE.MeshStandardMaterial({color:0xf4f1c8,emissive:0x000000,roughness:0.2,transparent:true,opacity:0.9});
const led=new THREE.Mesh(new THREE.SphereGeometry(2.6,20,14),ledMat); led.position.set(ledR*Math.cos(ledAz),ledH,ledR*Math.sin(ledAz)); scene.add(led);
const ledLight=new THREE.PointLight(0xfff3a0,0,90); ledLight.position.copy(led.position); scene.add(ledLight);
// dimension overlay
const dims=new THREE.Group(); dims.visible=false; scene.add(dims);
function dimLine(a,b,label){
  const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a),new THREE.Vector3(...b)]);
  dims.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0xb43c2a})));
  const c=document.createElement("canvas"); c.width=256;c.height=64; const x=c.getContext("2d");
  x.fillStyle="rgba(255,255,255,0.85)";x.fillRect(0,8,256,48);x.fillStyle="#b43c2a";x.font="28px IBM Plex Mono, monospace";x.fillText(label,10,42);
  const s=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),depthTest:false})); s.scale.set(40,10,1);
  s.position.set((a[0]+b[0])/2,(a[1]+b[1])/2+6,(a[2]+b[2])/2); dims.add(s);
}
dimLine([-48,0,-48],[-48,91.6,-48],"91.6 mm");
dimLine([-32,GEO.cupTop+16,0],[32,GEO.cupTop+16,0],"Ø 61–67 mm");
dimLine([-37.8,1,0],[37.8,1,0],"Ø 75.6 mm");
document.getElementById("dims").addEventListener("click",e=>{dims.visible=!dims.visible;e.currentTarget.setAttribute("aria-pressed",dims.visible)});

// ===================== time-series scope (same lanes as twin.html) =====================
const sc=document.getElementById("scope"), sx=sc.getContext("2d");
const RPM=30/Math.PI;
const LANES=[
  {key:"rpm",name:"回転数",unit:"rpm",live:l=>l.rpm,liveName:"実機 TEL",ser:[["ツイン",h=>Math.abs(h.w)*RPM,"--prop"],["目標",h=>h.ref||0,"--ink"]]},
  {key:"v",name:"電圧",unit:"V",ser:[["端子電圧",h=>h.vt,"--wire"],["逆起電力 K·ω",h=>h.emf,"--cool"]]},
  {key:"i",name:"電流",unit:"A",ser:[["平均 ⟨i⟩",h=>h.i,"--cool"],["実効値",h=>h.irms,"--muted"]]},
  {key:"T",name:"トルク",unit:"mN·m",ser:[["モーター K⟨i⟩",h=>h.Tm*1e3,"--prop"],["摩擦",h=>(h.Tfr+P.b*h.w)*1e3,"--muted"],["空力",h=>h.Tair*1e3,"--cool"],["加速 J·dω/dt",h=>h.Tacc*1e3,"--ok"]]},
  {key:"P",name:"電力",unit:"W",ser:[["電源から",h=>h.Psup,"--ink"],["機械へ K·ω·⟨i⟩",h=>h.Pem,"--prop"],["銅損 R⟨i²⟩",h=>h.Pcu,"--wire"],["L293D 損失",h=>h.Pdrv,"--warn"],["摩擦損",h=>h.Pfr,"--muted"],["空力",h=>h.Pair,"--cool"]]},
  {key:"F",name:"推力",unit:"gf",live:l=>liveThrust(l.filt),liveName:"実機回転数から",ser:[["推力 kT·ω²",h=>h.thr,"--ok"]]},
  {key:"d",name:"duty",unit:"%",live:l=>l.duty/255*100,liveName:"実機",ser:[["duty",h=>Math.abs(h.duty)/255*100,"--muted"]]},
];
const laneOn={rpm:true,v:true,i:true,T:true,P:true,F:true,d:false};
(function(){const el=document.getElementById("lanesel");
  for(const L of LANES){const id="lane_"+L.key, lab=document.createElement("label");
    lab.innerHTML=`<input type="checkbox" id="${id}" ${laneOn[L.key]?"checked":""}> ${L.name}`+L.ser.map(x=>`<i style="background:var(${x[2]})" title="${x[0]}"></i>`).join("");
    lab.querySelector("input").addEventListener("change",e=>{laneOn[L.key]=e.target.checked});el.appendChild(lab)}})();
function niceStep(span){const p=Math.pow(10,Math.floor(Math.log10(span/3))),m=span/3/p;return (m<1.5?1:m<3.5?2:m<7.5?5:10)*p}
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

// ===================== loop =====================
function resize(){const w=stage.clientWidth,h=stage.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}
new ResizeObserver(resize).observe(stage); resize();
const $=id=>document.getElementById(id);
// ---- one-screen dashboard: 3D view + scope fill the viewport on wide screens ----
function fitDash(){const d=document.getElementById("dash"); if(!d)return;
  if(window.innerWidth<=880){d.style.height="";return}
  const top=d.getBoundingClientRect().top+window.scrollY; d.style.height=Math.max(560,window.innerHeight-top-14)+"px"}
window.addEventListener("resize",fitDash); fitDash();
let last=performance.now();
function frame(now){
  const real=Math.min(0.05,(now-last)/1000); last=now;
  advance(real*($("slow").checked?0.25:1));
  // rotor pose with 1/60 s exposure blur: NG copies spread over the angle swept in the exposure
  const blur=$("blur").checked, sweepA=S.w*(1/60);
  ghosts.forEach((g,k)=>{
    const f=blur?k/NG:0; g.rotation.y=-(S.th-sweepA*f);
    const op=blur&&Math.abs(sweepA)>0.05?Math.min(1,1.6/NG+0.02):(k===0?1:0);
    g.visible=op>0&&rotorKind==="prop"; g.children.forEach(m=>{m.material.opacity=op;m.material.depthWrite=op>=1});
  });
  flag.rotation.y=-S.th;
  const on=S.t<ledUntil; ledMat.emissive.setHex(on?0xfff06a:0x000000); ledLight.intensity=on?1.6:0;
  $("clock").textContent=S.t.toFixed(3)+" s"; $("r_rpm").textContent=(Math.abs(S.w)*30/Math.PI).toFixed(0);
  $("r_i").textContent=S.i.toFixed(2); $("r_d").textContent=fw.on&&!fw.brake?fw.duty:0;
  const mc=$("modechip"); mc.textContent=S.mode; mc.className="mode "+S.mode;
  $("r_v").textContent=S.vt.toFixed(2); $("r_p").textContent=S.Psup.toFixed(3); $("r_f").textContent=(P.kT*S.w*S.w/9.80665*1000).toFixed(2);
  drawScope();
  controls.update(); renderer.render(scene,camera); requestAnimationFrame(frame);
}
updateJ();
// open in a working state: the new boot sequence
resetSim(true); log("# ブートシーケンス(5 s: 50→100 %, 11 s 停止)");
requestAnimationFrame(frame);
