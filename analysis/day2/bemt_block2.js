// ---- propeller aerodynamics: hover BEMT, same as twin/bemt.py (geometry measured: CHORD outline, pitch 18 deg from the IMG_5778 scan) ----
// direction: forward blows air up (away from the cup); reverse blows it down onto the cup top (Ø49.6 mm, 14 mm below):
// partial ground effect (Cheeseman-Bennett x share of the flow over the cup) and the cup catches eta of that jet.
const BEMT={rho:1.20,nu:1.52e-5,R:0.032,hub:0.345,B:3,N:40,zCup:0.014,rCup:0.0248,eta:0.8,
  chord:[[0.34,0.25],[0.40,0.311],[0.45,0.359],[0.50,0.396],[0.55,0.417],[0.60,0.442],[0.65,0.459],[0.70,0.46],[0.75,0.461],[0.80,0.454],[0.85,0.433],[0.90,0.381],[0.95,0.235],[1.0,0]]};
function bemtPass(w,pitchDeg,kL,kD,cam,kG){
  const {rho,nu,R,hub,B,N}=BEMT, th=pitchDeg*Math.PI/180, dx=(1-hub)/N;
  let T=0,Qi=0,Qp=0,md=0,mdIn=0,Pi=0,Tin=0;
  const half=x=>{const t=BEMT.chord;for(let k=1;k<t.length;k++)if(x<=t[k][0])return t[k-1][1]+(t[k][1]-t[k-1][1])*(x-t[k-1][0])/(t[k][0]-t[k-1][0]);return 0};
  for(let j=0;j<N;j++){
    const x=hub+(1-hub)*(j+0.5)/N, c=2*half(x)*R, r=x*R, Ut=w*r;
    const el=phi=>{const s=Math.sin(phi), F=(2/Math.PI)*Math.acos(Math.exp(-B/2*(1-x)/(x*s)))*(2/Math.PI)*Math.acos(Math.exp(-B/2*(x-hub)/(x*s)));
      const U2=Ut*Ut/Math.cos(phi)**2, a=th-phi, cl=kL*2*Math.PI*(a+2*cam), cd=kD*(2.656/Math.sqrt(Math.max(Math.sqrt(U2)*c/nu,1))+2*Math.sin(a)**2);
      return {f:4*Math.PI*r*F*(Ut*Math.tan(phi)/kG)**2-0.5*U2*B*c*(cl*Math.cos(phi)-cd*s),F,U2,cl,cd}};
    let lo=1e-5,hi=th+2*Math.max(cam,0); for(let it=0;it<60;it++){const m=0.5*(lo+hi); if(el(m).f<0)lo=m; else hi=m}
    const phi=0.5*(lo+hi), e=el(phi), q=0.5*rho*e.U2*B*c*R*dx, dT=q*(e.cl*Math.cos(phi)-e.cd*Math.sin(phi)), v=Ut*Math.tan(phi), dm=rho*2*Math.PI*r*R*dx*v*e.F;
    T+=dT; Qi+=q*e.cl*Math.sin(phi)*r; Qp+=q*e.cd*Math.cos(phi)*r/kD; md+=dm; Pi+=dT*v; if(r<BEMT.rCup){mdIn+=dm;Tin+=dT}
  }
  return {T,Qi,Qp,vw:md>0?T/md:0,Pind:Pi,phiCup:md>0?mdIn/md:0,Tin};
}
function bemtSolve(w,pitchDeg,kL,kD,camber){ // w signed (direction); magnitudes + bal = signed balance force (+ = reading rises)
  const d=w>=0?1:-1, cam=d*camber; let s, kG=1;
  if(d>0)s=bemtPass(Math.abs(w),pitchDeg,kL,kD,cam,1);
  else{let ph=0.5; for(let it=0;it<4;it++){kG=1-(BEMT.R/(4*BEMT.zCup))**2*ph; s=bemtPass(Math.abs(w),pitchDeg,kL,kD,cam,kG); ph=s.phiCup}}
  s.kG=kG; s.bal=d>0?s.T:-(s.T-BEMT.eta*s.Tin); return s;
}
let AERO=null; // tables over |w| (rad/s) for both directions, rebuilt when pitch / kL / kD / camber change
function buildAero(){const W=[];for(let k=0;k<=20;k++)W.push(25*k);
  AERO={w:W};
  for(const [d,suf] of [[1,""],[-1,"_r"]]){for(const k of ["kT","kQi","kQp","kV","kB"])AERO[k+suf]=[];
    for(const w of W){const we=Math.max(w,5), s=bemtSolve(d*we,P.pitch,P.kL,P.kD,P.camber);
      AERO["kT"+suf].push(s.T/we/we);AERO["kQi"+suf].push(s.Qi/we/we);AERO["kQp"+suf].push(s.Qp/we/we);AERO["kV"+suf].push(s.vw/we);AERO["kB"+suf].push(s.bal/we/we)}}}
function aeroAt(w){ // -> [signed thrust N (+ = air up), load torque magnitude N m, far-wake speed m/s, balance force N]; propeller off -> zeros
  if(!P.prop)return [0,0,0,0];
  const W=AERO.w, x=Math.min(Math.abs(w)/(W[1]-W[0]),W.length-1.000001), k=Math.floor(x), f=x-k, suf=w>=0?"":"_r", L=n=>{const a=AERO[n+suf];return a[k]+(a[k+1]-a[k])*f}, sg=w>=0?1:-1;
  return [sg*L("kT")*w*w,(L("kQi")+P.kD*L("kQp"))*w*w,L("kV")*Math.abs(w),L("kB")*w*w]}
