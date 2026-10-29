import numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
d=np.load('cyl.npz'); X=d['X']; R=0.18
r=np.hypot(X[:,0],X[:,1]); phi=np.arctan2(X[:,1],X[:,0])
xs=[0.40,0.50,0.60,0.70,0.80,0.90]
fig,ax=plt.subplots(len(xs),1,figsize=(15,14))
for k,x in enumerate(xs):
    m=np.abs(r/R-x)<0.015
    ax[k].scatter(phi[m]*x,X[m,2]/R,s=3); ax[k].set_xlim(-np.pi*x,np.pi*x); ax[k].set_ylim(-0.05,0.45)
    ax[k].set_aspect('equal'); ax[k].grid(alpha=.3); ax[k].set_ylabel('r/R=%.1f'%x)
ax[-1].set_xlabel('arc s/R (z/R vertical, true aspect)')
plt.tight_layout(); plt.savefig('sect.png',dpi=65)
