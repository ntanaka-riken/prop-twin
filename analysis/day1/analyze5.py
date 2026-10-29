import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, sys
S=sys.argv[1]
fs,a=wf.read(S+"/audio.wav"); a=a.astype(float)
def hsum(t0,w,f0s,lo=2000,hi=14000):
    i0=int(round(t0*fs)); n=int(round(w*fs)); x=a[i0:i0+n]*np.hanning(n)
    N=1<<18; X=np.abs(np.fft.rfft(x,N))**2; f=np.fft.rfftfreq(N,1/fs)
    L=np.log(X+1e-9); fm=f[::8]; L-=np.interp(f,fm,sg.medfilt(L[::8],51))  # whiten
    df=f[1]; out=[]
    for f0 in f0s:
        k=np.arange(np.ceil(lo/f0),np.floor(hi/f0)); idx=np.round(k*f0/df).astype(int)
        out.append(L[idx].mean())
    return np.array(out)
f0s=np.arange(35,75,0.02)
res=[]
for t0 in np.arange(2.7,5.6,0.05):
    h=hsum(t0,0.2,f0s); i=np.argmax(h); z=(h[i]-np.median(h))/h.std()
    res.append((t0+0.1,f0s[i],z)); print("%.2f  f0=%.2f Hz  z=%.1f"%(t0+0.1,f0s[i],z))
np.save(S+"/audio_f0.npy",np.array(res))
