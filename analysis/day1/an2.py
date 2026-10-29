import cv2, numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, sys, json
S,V=sys.argv[1],sys.argv[2]
v=cv2.VideoCapture(V); fps=v.get(5)
cx,cy=int(463/.4),int(313/.4); r=40
led=[];yel=[]
while True:
    ok,f=v.read()
    if not ok: break
    roi=f[cy-r:cy+r,cx-r:cx+r].astype(float)
    led.append(roi.max(axis=2).mean())
    h=cv2.cvtColor(f[100:700,400:1250],cv2.COLOR_BGR2HSV)
    yel.append(((h[...,1]>150)&(h[...,0]>20)&(h[...,0]<40)).mean())
led=np.array(led); yel=np.array(yel); t=(np.arange(len(led))+0.5)/fps
base=np.median(led); d=led-base
thr=base+0.5*(d.max()); on=led>thr
edges=np.flatnonzero(np.diff(on.astype(int))==1)+1
print("LED base %.1f max %.1f; flashes at frames"%(base,led.max()),list(edges),"t=",[round(e/fps,3) for e in edges])
for e in edges: print("  frame %d: "%e, " ".join("%.0f"%x for x in led[e-2:e+9]))
np.save(S+"/trace2.npy",np.c_[t,led,yel])
# yellow frac transitions
print("yel frac every 1s:"," ".join("%.2f"%yel[int(k*fps)] for k in range(int(len(yel)/fps))))
fs,a=wf.read(S+"/audio2.wav"); a=a.astype(float)
# beeps: Tink -> find band with transient; use 3-6 kHz onsets
x=sg.sosfiltfilt(sg.butter(4,[2500,6000],'bp',fs=fs,output='sos'),a)
env=np.sqrt(np.convolve(x**2,np.ones(240)/240,'same'))
pk,_=sg.find_peaks(env,height=np.percentile(env,99.5)*0.8,distance=fs*0.5)
print("beep-ish peaks t=",[round(p/fs,3) for p in pk][:20])
