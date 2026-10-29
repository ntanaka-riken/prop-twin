import cv2, numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt, sys
S=sys.argv[1]; V=sys.argv[2]
v=cv2.VideoCapture(V); fps=v.get(5)
# propeller ROI in full-res (from 0.4x preview: x150-420, y45-240)
x0,x1,y0,y1=int(150/.4),int(420/.4),int(45/.4),int(240/.4)
yel=[];diff=[];prev=None
while True:
    ok,f=v.read()
    if not ok: break
    r=f[y0:y1,x0:x1]; h=cv2.cvtColor(r,cv2.COLOR_BGR2HSV)
    m=(h[...,0]>20)&(h[...,0]<40)&(h[...,1]>150)&(h[...,2]>120)
    yel.append(m.mean())
    g=cv2.cvtColor(r,cv2.COLOR_BGR2GRAY).astype(float)
    diff.append(0 if prev is None else np.abs(g-prev).mean()); prev=g
t=np.arange(len(yel))/fps
fs,a=wf.read(S+"/audio.wav"); a=a.astype(float)
f,tt,Z=sg.spectrogram(a,fs,nperseg=4096,noverlap=3584)
fig,ax=plt.subplots(3,1,figsize=(11,10),sharex=True)
ax[0].plot(t,yel);ax[0].set_ylabel("saturated-yellow frac")
ax[1].plot(t,diff);ax[1].set_ylabel("frame diff")
ax[2].pcolormesh(tt,f,10*np.log10(Z+1e-9),shading="auto",vmin=np.percentile(10*np.log10(Z+1e-9),40));ax[2].set_ylim(0,3000);ax[2].set_ylabel("Hz")
ax[2].set_xlabel("s");plt.tight_layout();plt.savefig(S+"/overview.png",dpi=80)
np.save(S+"/vid.npy",np.c_[t,yel,diff])
# audio RMS envelope
env=np.sqrt(np.convolve(a**2,np.ones(2400)/2400,"same"))
for ti in np.arange(0,7.7,0.25): print("%.2f rms=%.0f"%(ti,env[int(ti*fs)]), "yel=%.3f diff=%.1f"%(yel[min(int(ti*fps),len(yel)-1)],diff[min(int(ti*fps),len(yel)-1)]))
