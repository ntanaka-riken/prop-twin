import numpy as np
from scipy.optimize import brentq
rho,nu=1.20,1.5e-5; R=0.032; B=3
CH=np.array([[0.34,0.25],[0.40,0.311],[0.45,0.359],[0.50,0.396],[0.55,0.417],[0.60,0.442],[0.65,0.459],[0.70,0.46],[0.75,0.461],[0.80,0.454],[0.85,0.433],[0.90,0.381],[0.95,0.235],[1.0,0.02]])
x=np.linspace(0.345,0.99,60); dx=x[1]-x[0]
c=2*np.interp(x,CH[:,0],CH[:,1])*R   # chord = 2 x half-width
def polar(a,Re):  # thin cambered plate, low Re
    cl=np.clip(0.9*2*np.pi*a,-0.9,0.9)+0.0; cd=1.3/np.sqrt(Re)*2+1.0*np.sin(a)**2+0.01
    return cl,cd
def bemt(w,th):
    T=Q=0.
    for xi,ci,ti in zip(x,c,th):
        r=xi*R; sig=B*ci/(2*np.pi*r)
        def res(phi):
            a=ti-phi; U=w*r/np.cos(phi); cl,cd=polar(a,U*ci/nu)
            f=B/2*(1-xi)/(xi*np.sin(phi)+1e-9); F=2/np.pi*np.arccos(np.exp(-f))
            # momentum: 4F sin^2phi = sig*(cl cos - cd sin)  (hover, vi = w r tan phi)
            return 4*F*np.sin(phi)**2 - sig*(cl*np.cos(phi)-cd*np.sin(phi))/np.cos(phi)**0*1
        try: phi=brentq(res,1e-4,ti) if res(1e-4)<0<res(ti) or res(1e-4)*res(ti)<0 else 1e-4
        except Exception: phi=1e-4
        a=ti-phi; U=w*r/np.cos(phi); cl,cd=polar(a,U*ci/nu)
        dL=0.5*rho*U**2*ci*cl; dD=0.5*rho*U**2*ci*cd
        T+=B*(dL*np.cos(phi)-dD*np.sin(phi))*dx*R; Q+=B*(dL*np.sin(phi)+dD*np.cos(phi))*r*dx*R
    return T,Q
w=2*np.pi*52.7
print("Tmeas=%.4f N  Qmodel(c w^2)=%.2e  (b+c)=%.2e"%(1.7e-7*w*w,2.848e-9*w*w,2.848e-9*w*w+3.616e-7*w))
for th0 in [6,8,10,12,15,18,22]:
    th=np.deg2rad(th0+ 0*x); T,Q=bemt(w,th)
    print("flat pitch %2d deg: T=%.4f N (%.2f gf)  Q=%.2e  kT=%.2e c=%.2e"%(th0,T,T/9.80665e-3,Q,T/w**2,Q/w**2))
