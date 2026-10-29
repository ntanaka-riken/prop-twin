import numpy as np, cv2
from scipy.spatial import cKDTree
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation as Rot
d=np.load('frame.npz'); Q,yel,col=d['Q'],d['yellow'],d['col']
hsv=cv2.cvtColor(col.astype(np.uint8)[None],cv2.COLOR_BGR2HSV)[0].astype(float)
prop=(hsv[:,0]>8)&(hsv[:,0]<40)&(hsv[:,1]>90)&(hsv[:,2]>80)&(Q[:,2]>0.002)
P=Q[prop]; ctr=np.r_[np.median(P[:,:2],0)]
P=P[np.hypot(*(P[:,:2]-ctr).T)<0.25]
tree=cKDTree(P)
def cost(x):
    th,ph,cx,cy,cz=x; a=np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)]); c=np.array([cx,cy,cz])
    tot=0
    for ang in (2*np.pi/3,-2*np.pi/3):
        Rm=Rot.from_rotvec(a*ang).as_matrix(); P2=(P-c)@Rm.T+c
        dd,_=tree.query(P2); tot+=np.mean(np.minimum(dd,0.03)**2)
    return tot
best=None
for th0 in np.radians([0,10,20]):
  for ph0 in np.radians(range(0,360,45)):
    r=minimize(cost,[th0,ph0,ctr[0],ctr[1],0.04],method='Nelder-Mead',options=dict(maxiter=3000,xatol=1e-5,fatol=1e-10))
    if best is None or r.fun<best.fun: best=r
th,ph,cx,cy,cz=best.x; a=np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
if a[2]<0: a=-a
print('axis tilt from table normal %.1f deg, rms %.4f units'%(np.degrees(np.arccos(a[2])),np.sqrt(best.fun/2)))
np.savez('axis.npz',a=a,c=np.array([cx,cy,cz]),P=P)
