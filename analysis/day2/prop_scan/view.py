import numpy as np, cv2, sys
exec(open('blade_pitch.py').read().split('# hub centre')[0].replace("obj, tex = sys.argv[1], sys.argv[2]","obj, tex = 'prop.obj','Texture_diffuseColor.png'"))
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
np.savez('frame.npz', Q=Q, yellow=yellow, col=col)
fig,ax=plt.subplots(1,2,figsize=(14,7))
sub=np.random.default_rng(1).choice(len(Q),min(len(Q),40000),replace=False)
ax[0].scatter(Q[sub,0],Q[sub,1],c=col[sub][:,::-1]/255,s=1); ax[0].set_aspect('equal'); ax[0].set_title('top (true colour)')
Yq=Q[yellow]; s=ax[1].scatter(Yq[:,0],Yq[:,1],c=Yq[:,2],s=1,cmap='viridis'); ax[1].set_aspect('equal'); plt.colorbar(s,ax=ax[1]); ax[1].set_title('yellow, height')
plt.savefig('view.png',dpi=80)
print(np.ptp(Q,0))
