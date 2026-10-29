import numpy as np, sys
exec(open("analyze5.py").read().split("f0s=np.arange")[0])
f0s=np.arange(8,60,0.05)
for (lo,hi,w) in [(1000,6000,0.08),(2000,10000,0.06)]:
    print("band",lo,hi,"win",w)
    for t0 in np.arange(2.80,3.70,0.04):
        h=hsum(t0,w,f0s,lo,hi); i=np.argmax(h); z=(h[i]-np.median(h))/h.std()
        print("%.3f  f0=%.2f  z=%.1f"%(t0+w/2,f0s[i],z))
