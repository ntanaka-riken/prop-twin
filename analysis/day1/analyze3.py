import numpy as np, scipy.io.wavfile as wf, scipy.signal as sg, matplotlib, sys
matplotlib.use("Agg"); import matplotlib.pyplot as plt
S=sys.argv[1]
fs,a=wf.read(S+"/audio.wav"); a=a.astype(float)
a=sg.sosfilt(sg.butter(4,300,'hp',fs=fs,output='sos'),a)
f,tt,Z=sg.spectrogram(a,fs,nperseg=2048,noverlap=1792)
L=10*np.log10(Z+1e-9); L-=np.median(L[:,(tt<2.5)|(tt>6)],axis=1,keepdims=True)
fig,ax=plt.subplots(2,1,figsize=(12,9))
ax[0].pcolormesh(tt,f,L,shading="auto",vmin=0,vmax=25,cmap="magma");ax[0].set_ylim(0,16000);ax[0].set_ylabel("Hz (bg-subtracted)")
ax[1].pcolormesh(tt,f,L,shading="auto",vmin=0,vmax=25,cmap="magma");ax[1].set_ylim(0,3000);ax[1].set_xlim(2.5,6)
plt.tight_layout();plt.savefig(S+"/spec_bg.png",dpi=75)
