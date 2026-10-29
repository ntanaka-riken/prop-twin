import numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
d=np.load('axis.npz'); a,c,P=d['a'],d['c'],d['P']
ex=np.cross(a,[0,1,0]); ex/=np.linalg.norm(ex); ey=np.cross(a,ex)
X=np.c_[(P-c)@ex,(P-c)@ey,(P-c)@a]; X[:,2]-=X[:,2].min()
r=np.hypot(X[:,0],X[:,1]); phi=np.arctan2(X[:,1],X[:,0]); R=np.percentile(r,99.5)
print('R units',R,'z range',np.ptp(X[:,2]),'hub top/R',X[r<0.3*R,2].max()/R)
np.savez('cyl.npz',X=X,R=R)
fig,ax=plt.subplots(4,1,figsize=(15,12))
for k,x in enumerate([0.45,0.6,0.75,0.9]):
    m=np.abs(r/R-x)<0.015
    ax[k].scatter(phi[m]*x,X[m,2]/R,s=2); ax[k].set_ylabel('z/R @ r/R=%.2f'%x); ax[k].set_xlim(-np.pi*x,np.pi*x)
    ax[k].set_aspect("equal"); ax[k].grid(alpha=.3)
ax[-1].set_xlabel('arc s/R')
plt.tight_layout(); plt.savefig('unwrap.png',dpi=70)
