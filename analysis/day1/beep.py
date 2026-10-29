import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, sys, json
S=sys.argv[1]
fs,t=wf.read(S+"/tink.wav"); t=t.astype(float); t=t[:int(0.15*fs)]
def find(wav,host,off_guess=None):
    fs,a=wf.read(wav); a=a.astype(float)
    b=sg.butter(4,[1500,9000],'bp',fs=fs,output='sos'); A=sg.sosfiltfilt(b,a); T=sg.sosfiltfilt(b,t)
    c=sg.fftconvolve(A,T[::-1],'valid'); 
    env=np.sqrt(sg.fftconvolve(A**2,np.ones(len(T)),'valid'))+1e-9
    ncc=c/(env*np.linalg.norm(T))
    pk,_=sg.find_peaks(ncc,height=None,distance=int(0.5*fs))
    pk=pk[np.argsort(ncc[pk])[::-1][:40]]; print("  top ncc",np.round(np.sort(ncc[pk])[::-1][:20],2)); tp=np.sort(pk)/fs
    h=json.load(open(host)); hb=[x[0] for x in h if x[1]=="beep"]
    best=None
    for off in np.arange(-5,30,0.002):
        m=[np.min(np.abs(tp-(x+off))) for x in hb]; sc=sum(min(mm,0.05) for mm in m)
        if best is None or sc<best[0]: best=(sc,off,m)
    sc,off,m=best
    pairs=[(x,tp[np.argmin(np.abs(tp-(x+off)))]) for x,mm in zip(hb,m) if mm<0.02]
    d=[p-x for x,p in pairs]
    return np.mean(d),np.std(d),len(pairs),len(hb),[round(float(ncc[int(p*fs)]),2) for x,p in pairs]
for name,w,h in [("5744",S+"/audio44.wav","~/blink_ota_esp8266_v36/twin/data/JK_nocoin_hostlog.json"),
                 ("5745",S+"/audio45.wav","~/blink_ota_esp8266_v36/twin/data/JK_coin_hostlog.json"),
                 ("5742",S+"/audio2.wav","~/blink_ota_esp8266_v36/twin/data/sustain20_hostlog.json")]:
    m,s,n,N,cc=find(w,h); print(name,"beep offset (audio - host beep) %.4f sd %.4f matched %d/%d ncc %s"%(m,s,n,N,cc))
