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
