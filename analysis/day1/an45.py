import sys, json, numpy as np; sys.path.insert(0,".")
import identify as idf, scipy.io.wavfile as wf
S="/private/tmp/claude-501/-Users-USER-blink-ota-esp8266-v36/4ccccbbb-9307-4e71-804f-1160f86304e6/scratchpad"
V="~/Downloads/IMG_5745.MOV"
fs,a=wf.read(S+"/audio45.wav"); a=a.astype(float)
h=json.load(open("data/JK_coin_hostlog.json")); tx=[(x[0],x[2]) for x in h if x[1]=="tx"]
stops=[(t,c) for t,c in tx if c in ("dcm:off","dcm:brake") and [x for x in tx if x[0]<t][-1][1]=="dcm:speed 255"]
f0s=np.arange(31,39,0.02); offs=[]; ff=[]
for t,c in stops:
    zs=[]
    for tc in np.arange(t+9.37-0.6,t+9.37+0.3,0.01):
        hh=idf.harmonic_sum(a,fs,tc-0.05,0.1,f0s); zs.append((tc,(hh.max()-np.median(hh))/hh.std(),f0s[np.argmax(hh)]))
    zmax=np.median([z for _,z,_ in zs[:25]])
    e=next((tc for tc,z,f in zs if z<0.5*zmax),None)
    f=np.median([f for _,_,f in zs[:25]])
    print("%-10s host %.3f zmax %.1f f=%.2f Hz comb end %s"%(c,t,zmax,f,"%.3f -> off %.3f"%(e,e-t-0.040) if e else "-"))
    if e and zmax>6: offs.append(e-t-0.040)
    ff.append(f)
off=float(np.median(offs)); print("offset (LED-equivalent) median %.3f  values %s"%(off,np.round(offs,3)))
json.dump({"off":off,"f_full":ff},open(S+"/off45.json","w"))
