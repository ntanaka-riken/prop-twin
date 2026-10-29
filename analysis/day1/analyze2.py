import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, matplotlib, cv2, sys
matplotlib.use("Agg"); import matplotlib.pyplot as plt
S=sys.argv[1]; V=sys.argv[2]
fs,a=wf.read(S+"/audio.wav"); a=a.astype(float)
def spec(t0,t1):
    f,P=sg.welch(a[int(t0*fs):int(t1*fs)],fs,nperseg=8192); return f,P
f,Pon=spec(3.0,5.0); _,Poff1=spec(0.3,2.6); _,Poff2=spec(5.8,7.6)
Poff=np.minimum(Poff1,Poff2); R=10*np.log10(Pon/(Poff+1e-12))
fig,ax=plt.subplots(2,1,figsize=(11,7))
ax[0].semilogy(f,Pon,label="on 3-5s");ax[0].semilogy(f,Poff,label="off");ax[0].set_xlim(0,12000);ax[0].legend()
ax[1].plot(f,R);ax[1].set_xlim(0,12000);ax[1].set_ylabel("on/off dB")
plt.tight_layout();plt.savefig(S+"/spec_onoff.png",dpi=80)
idx=np.argsort(R*(f>50))[::-1]
seen=[]
for i in idx:
    if all(abs(f[i]-s)>30 for s in seen): seen.append(f[i]); print("%.0f Hz  +%.1f dB  P=%.2e"%(f[i],R[i],Pon[i]))
    if len(seen)>=15: break
# montage of spin-down frames
v=cv2.VideoCapture(V); tiles=[]
x0,x1,y0,y1=int(150/.4),int(420/.4),int(45/.4),int(240/.4)
for i in range(150,174):
    v.set(1,i); ok,fr=v.read(); r=cv2.resize(fr[y0:y1,x0:x1],None,fx=.3,fy=.3)
    cv2.putText(r,str(i),(5,20),0,0.6,(0,0,255),2); tiles.append(r)
rows=[np.hstack(tiles[k:k+6]) for k in range(0,24,6)]
cv2.imwrite(S+"/spindown.jpg",np.vstack(rows))
tiles=[]
for i in range(80,92):
    v.set(1,i); ok,fr=v.read(); r=cv2.resize(fr[y0:y1,x0:x1],None,fx=.3,fy=.3)
    cv2.putText(r,str(i),(5,20),0,0.6,(0,0,255),2); tiles.append(r)
cv2.imwrite(S+"/spinup.jpg",np.vstack([np.hstack(tiles[:6]),np.hstack(tiles[6:])]))
