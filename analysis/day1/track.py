import cv2, numpy as np, sys
V=sys.argv[1]; v=cv2.VideoCapture(V)
def frame(i): v.set(1,i); return v.read()[1]
def ymask(f):
    h=cv2.cvtColor(f,cv2.COLOR_BGR2HSV)
    return ((h[...,0]>18)&(h[...,0]<42)&(h[...,1]>60)&(h[...,2]>120)).astype(np.uint8)
# disc ellipse from a full-speed blurred frame: union of yellow over frames 100-130
acc=np.zeros(frame(0).shape[:2],np.float32)
for i in range(100,130): acc+=ymask(frame(i))
m=(acc>8).astype(np.uint8); m[:, :300]=0; m[:, 1150:]=0; m[700:,:]=0
cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE); c=max(cs,key=cv2.contourArea)
(cx,cy),(MA,ma),ang=cv2.fitEllipse(c); print("ellipse",cx,cy,MA,ma,ang)
np.save("ellipse.npy",[cx,cy,MA,ma,ang])
# unwarp to circle, polar profile of yellow (blades) in annulus 0.45-0.95 R
R=max(MA,ma)/2; th=np.deg2rad(ang)
def profile(f):
    y=ymask(f).astype(np.float32); prof=[]
    angs=np.deg2rad(np.arange(0,360,1.0)); rs=np.linspace(0.45,0.95,20)
    a=MA/2; b=ma/2
    for p in angs:
        u=rs*np.cos(p); w=rs*np.sin(p)   # unit-circle coords -> ellipse
        X=cx+a*u*np.cos(th)-b*w*np.sin(th); Y=cy+a*u*np.sin(th)+b*w*np.cos(th)
        prof.append(y[np.clip(Y.astype(int),0,y.shape[0]-1),np.clip(X.astype(int),0,y.shape[1]-1)].mean())
    return np.array(prof)
P={i:profile(frame(i)) for i in range(150,200)}
prev=None
for i in range(150,200):
    p=P[i]-P[i].mean(); contrast=P[i].std()
    if prev is not None:
        cc=[np.dot(np.roll(prev,k),p) for k in range(-60,60)]  # 3 blades: +-60 deg unambiguous
        k=np.argmax(cc)-60
        print(i,"contrast %.3f  dtheta %+d deg/frame"%(contrast,k))
    prev=p
cv2.imwrite("ellipse.jpg",cv2.ellipse(frame(170).copy(),((cx,cy),(MA,ma),ang),(0,0,255),3)[::2,::2])
