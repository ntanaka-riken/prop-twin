import sys, numpy as np
sys.argv=[sys.argv[0]]; sys.path.insert(0,".")
import identify as idf
fs,a=idf.load_audio("~/Downloads/IMG_5742.MOV")
f0s=np.arange(8,75,0.02)
for t0 in np.arange(7.6,13.0,0.05):
    w=0.2 if t0<10.8 else 0.1
    h=idf.harmonic_sum(a,fs,t0,w,f0s); j=np.argmax(h); z=(h[j]-np.median(h))/h.std()
    print("%.3f f0=%6.2f z=%5.1f"%(t0+w/2,f0s[j],z))
