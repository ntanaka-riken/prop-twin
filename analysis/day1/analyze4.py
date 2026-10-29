import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, matplotlib, sys
matplotlib.use("Agg"); import matplotlib.pyplot as plt
S=sys.argv[1]
fs,a=wf.read(S+"/audio.wav"); a=a.astype(float)
def comb(t0,t1,lo=3000,hi=14000,nper=None):
    x=a[int(t0*fs):int(t1*fs)]; n=nper or len(x)
    f,P=sg.welch(x,fs,nperseg=min(n,len(x)),window="hann")
    m=(f>lo)&(f<hi); L=np.log(P[m]); L=L-sg.medfilt(L,101)  # flatten
    df=f[1]-f[0]; ac=np.correlate(L,L,"full")[len(L)-1:]; lag=np.arange(len(ac))*df
    return f[m],L,lag,ac
f,L,lag,ac=comb(3.1,4.9)
sel=(lag>40)&(lag<1500)
pk,_=sg.find_peaks(ac[sel],distance=5); order=np.argsort(ac[sel][pk])[::-1][:10]
print("autocorr peaks (Hz):",[round(lag[sel][pk][o],1) for o in order])
fig,ax=plt.subplots(2,1,figsize=(12,7))
ax[0].plot(f,L,lw=.5);ax[0].set_xlim(6000,9000)
ax[1].plot(lag[sel],ac[sel]);plt.tight_layout();plt.savefig(S+"/comb.png",dpi=75)
# time-resolved fundamental via spectral autocorr, 0.25 s windows
for t0 in np.arange(2.8,5.6,0.1):
    f,L,lag,ac=comb(t0,t0+0.3)
    sel=(lag>60)&(lag<600); i=np.argmax(ac[sel]); print("%.2f  peak lag %.0f Hz  strength %.2f"%(t0+0.15,lag[sel][i],ac[sel][i]/ac[0]))
