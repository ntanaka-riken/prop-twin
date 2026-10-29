import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, sys, json
S=sys.argv[1]; wavp=sys.argv[2]; segs=json.loads(sys.argv[3]); out=sys.argv[4]
fs,a=wf.read(wavp); a=a.astype(float)
def score(tc,w,f0s,s,lo=6000,hi=15000):
    n=int(w*fs); t=np.arange(-n,n)/fs           # window 2w centred on tc
    tau=t+s*t*t/2                                # warped time: f(t)=fc(1+s t)
    tg=np.linspace(tau[0],tau[-1],len(t))        # uniform in tau
    tsrc=np.where(abs(s)>1e-9,(-1+np.sqrt(np.maximum(1+2*s*tg,1e-12)))/s if abs(s)>1e-9 else tg,tg)
    i0=int(tc*fs); x=np.interp(tsrc*fs+i0,np.arange(len(a)),a)*np.hanning(len(tg))
    N=1<<17; X=np.abs(np.fft.rfft(x,N))**2; f=np.fft.rfftfreq(N,1/fs)
    L=np.log(X+1e-9); L-=np.interp(f,f[::8],sg.medfilt(L[::8],51))
    df=f[1]; out=np.empty(len(f0s))
    for j,f0 in enumerate(f0s):
        k=np.arange(np.ceil(lo/f0),np.floor(hi/f0)); out[j]=L[np.round(k*f0/df).astype(int)].mean()
    return out
res={}
for name,(t_from,t_to) in segs.items():
    tr=[]; prev=None
    for tc in np.arange(t_from,t_to,0.025):
        best=None
        fgrid=np.arange(4,58,0.05) if prev is None else np.arange(max(3,prev-6),min(60,prev+3),0.02)
        for s in np.arange(-6,0.51,0.5):
            h=score(tc,0.06,fgrid,s); j=np.argmax(h); z=(h[j]-np.median(h))/h.std()
            if best is None or z>best[2]: best=(fgrid[j],s,z)
        f0,s,z=best
        if z>5: prev=f0
        tr.append((round(tc,3),round(f0,2),s,round(z,1)))
        print(name,"%.3f f0=%6.2f s=%+.1f z=%.1f"%tr[-1],flush=True)
    res[name]=tr
json.dump(res,open(out,"w"))
