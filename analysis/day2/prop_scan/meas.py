import numpy as np
d=np.load('cyl.npz'); X=d['X']; R=0.18
r=np.hypot(X[:,0],X[:,1]); phi=np.arctan2(X[:,1],X[:,0])
CH=dict([(0.40,0.311),(0.45,0.359),(0.50,0.396),(0.55,0.417),(0.60,0.442),(0.65,0.459),(0.70,0.46),(0.75,0.461),(0.80,0.454),(0.85,0.433),(0.90,0.381)])
out=[]
print('r/R  blade  chord_s/R chordCHORD/R  dz/R  pitch  f/c')
for x in [0.40,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9]:
    m=np.abs(r/R-x)<0.015; s=np.sort(np.c_[(phi[m]%(2*np.pi))*x, X[m,2]/R],axis=0) if False else None
    p=(phi[m]+np.pi/2)%(2*np.pi); z=X[m,2]/R; o=np.argsort(p); p,z=p[o],z[o]
    # split into blades at angular gaps > 15 deg
    gap=np.where(np.diff(p)>np.radians(15))[0]; segs=np.split(np.arange(len(p)),gap+1)
    if p[0]+2*np.pi-p[-1]<np.radians(15) and len(segs)>1: segs=[np.r_[segs[-1],segs[0]]]+segs[1:-1]
    for k,sg in enumerate(segs):
        if len(sg)<25: continue
        pp=np.unwrap(p[sg]); s=pp*x; zz=z[sg]
        b=np.arange(s.min(),s.max()+0.02,0.02); idx=np.digitize(s,b)
        E=np.array([(s[idx==i].mean(),zz[idx==i].max()) for i in np.unique(idx)])
        if len(E)<6: continue
        # chord: endpoints of the upper envelope
        (s0,z0),(s1,z1)=E[0],E[-1]; c=np.hypot(s1-s0,z1-z0); th=np.degrees(np.arctan2(abs(z1-z0),abs(s1-s0)))
        t=np.array([s1-s0,z1-z0])/c; nrm=np.array([-t[1],t[0]]); dev=(E-[s0,z0])@nrm; f=dev[np.argmax(np.abs(dev))]/c
        if z1<z0: f=-f
        exp=2*CH.get(round(x,2),np.nan)
        out.append((x,k,c,exp,abs(z1-z0),th,f)); print('%.2f  %d   %.2f     %.2f       %.2f  %4.1f  %+.3f'%(x,k,c,exp,abs(z1-z0),th,f))
np.save('meas.npy',np.array(out))
