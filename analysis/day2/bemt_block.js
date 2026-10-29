// ---- propeller aerodynamics: hover BEMT, same as twin/bemt.py (geometry measured: CHORD outline, pitch 18 deg from the IMG_5778 scan) ----
const BEMT={rho:1.20,nu:1.52e-5,R:0.032,hub:0.345,B:3,N:40,
  chord:[[0.34,0.25],[0.40,0.311],[0.45,0.359],[0.50,0.396],[0.55,0.417],[0.60,0.442],[0.65,0.459],[0.70,0.46],[0.75,0.461],[0.80,0.454],[0.85,0.433],[0.90,0.381],[0.95,0.235],[1.0,0]]};
function bemtSolve(w,pitchDeg,kL,kD){ // -> {T,Qi,Qp(per unit kD),vw,Pind} in SI
  const {rho,nu,R,hub,B,N}=BEMT, th=pitchDeg*Math.PI/180, dx=(1-hub)/N;
  let T=0,Qi=0,Qp=0,md=0,Pi=0;
  const half=x=>{const t=BEMT.chord;for(let k=1;k<t.length;k++)if(x<=t[k][0])return t[k-1][1]+(t[k][1]-t[k-1][1])*(x-t[k-1][0])/(t[k][0]-t[k-1][0]);return 0};
  for(let j=0;j<N;j++){
    const x=hub+(1-hub)*(j+0.5)/N, c=2*half(x)*R, r=x*R, Ut=w*r;
    const el=phi=>{const s=Math.sin(phi), F=(2/Math.PI)*Math.acos(Math.exp(-B/2*(1-x)/(x*s)))*(2/Math.PI)*Math.acos(Math.exp(-B/2*(x-hub)/(x*s)));
      const U2=Ut*Ut/Math.cos(phi)**2, a=th-phi, cl=kL*2*Math.PI*a, cd=kD*(2.656/Math.sqrt(Math.max(Math.sqrt(U2)*c/nu,1))+2*Math.sin(a)**2);
      return {f:4*Math.PI*r*F*(Ut*Math.tan(phi))**2-0.5*U2*B*c*(cl*Math.cos(phi)-cd*s),F,U2,cl,cd}};
    let lo=1e-5,hi=th; for(let it=0;it<60;it++){const m=0.5*(lo+hi); if(el(m).f<0)lo=m; else hi=m}
    const phi=0.5*(lo+hi), e=el(phi), q=0.5*rho*e.U2*B*c*R*dx, dT=q*(e.cl*Math.cos(phi)-e.cd*Math.sin(phi)), v=Ut*Math.tan(phi);
    T+=dT; Qi+=q*e.cl*Math.sin(phi)*r; Qp+=q*e.cd*Math.cos(phi)*r/kD; md+=rho*2*Math.PI*r*R*dx*v*e.F; Pi+=dT*v;
  }
  return {T,Qi,Qp,vw:md>0?T/md:0,Pind:Pi};
}
let AERO=null; // table over w (rad/s), rebuilt when pitch / kL change
function buildAero(){const W=[];for(let k=0;k<=20;k++)W.push(25*k);
  AERO={w:W,kT:[],kQi:[],kQp:[],kV:[]};
  for(const w of W){const we=Math.max(w,5), s=bemtSolve(we,P.pitch,P.kL,P.kD);
    AERO.kT.push(s.T/we/we);AERO.kQi.push(s.Qi/we/we);AERO.kQp.push(s.Qp/we/we);AERO.kV.push(s.vw/we)}}
function aeroAt(w){ // -> [thrust N, load torque magnitude N m, far-wake speed m/s]; propeller off -> zeros
  if(!P.prop)return [0,0,0];
  const W=AERO.w, x=Math.min(Math.abs(w)/(W[1]-W[0]),W.length-1.000001), k=Math.floor(x), f=x-k, L=a=>a[k]+(a[k+1]-a[k])*f;
  return [L(AERO.kT)*w*w,(L(AERO.kQi)+P.kD*L(AERO.kQp))*w*w,L(AERO.kV)*Math.abs(w)]}
