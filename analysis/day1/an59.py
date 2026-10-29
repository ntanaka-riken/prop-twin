import sys, json, numpy as np; sys.path.insert(0,".")
import identify as idf, scipy.io.wavfile as wf
S="/private/tmp/claude-501/-Users-USER-blink-ota-esp8266-v36/4ccccbbb-9307-4e71-804f-1160f86304e6/scratchpad"
fs,a=wf.read(S+"/audio59.wav"); a=a.astype(float)
f0s=np.arange(25,420,0.1)
out=[]
for tc in np.arange(8.2,31.0,0.1):
    h=idf.harmonic_sum(a,fs,tc-0.1,0.2,f0s,lo=1500,hi=15000)
    z=(h-np.median(h))/h.std(); j=np.argmax(z)
    # octave guard: lowest candidate within 90 % of the best score that is a sub-multiple
    cand=[k for k in range(1,5) if f0s[j]/k>=25]
    best=f0s[j]
    for k in cand[1:]:
        jj=np.argmin(abs(f0s-f0s[j]/k))
        if z[jj]>=0.9*z[j]: best=f0s[jj]
    out.append((round(tc,2),round(float(best),2),round(float(z[j]),1)))
for k in range(0,len(out),3): print("  ".join("%.1f:%6.1f/%4.1f"%x for x in out[k:k+3]))
json.dump(out,open(S+"/f59.json","w"))
