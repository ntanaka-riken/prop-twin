import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, matplotlib, sys
matplotlib.use("Agg"); import matplotlib.pyplot as plt
S=sys.argv[1]
fs,a=wf.read(S+"/audio44.wav"); a=a.astype(float)
a=sg.sosfilt(sg.butter(4,300,'hp',fs=fs,output='sos'),a)
f,tt,Z=sg.spectrogram(a,fs,nperseg=1024,noverlap=896)
L=10*np.log10(Z+1e-9); L-=np.median(L[:,(tt<8)],axis=1,keepdims=True)
fig,ax=plt.subplots(3,1,figsize=(12,10))
for k,(t0,t1) in enumerate([(11.5,13),(18.4,20),(25.4,27.2)]):
    ax[k].pcolormesh(tt,f,L,shading="auto",vmin=0,vmax=25,cmap="magma");ax[k].set_xlim(t0,t1);ax[k].set_ylim(0,16000)
plt.tight_layout();plt.savefig(S+"/sp44.png",dpi=70)
