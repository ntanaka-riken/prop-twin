import sys, numpy as np, json
sys.path.insert(0,".")
import identify as idf
V="~/Downloads/IMG_5744.MOV"
OFF=6.737
h=json.load(open("data/JK_nocoin_hostlog.json")); ev=[(x[0]+OFF,x[2]) for x in h if x[1]=="tx"]
for t,c in ev: print("event %.3f %s"%(t,c))
def track(f0,f1):
    r=idf.video_track(V,(285,345),(f0,f1),xlim=(380,1200),ylim=820)
    return r
def unwrap(steps,fps):
    st=[(i,d) for i,d,c in steps]
    # find stop: last nonzero step followed by zeros
    nz=[k for k,(i,d) in enumerate(st) if abs(d)>1]
    last=nz[-1]; out=[]; prev=st[last][1]
    for k in range(last,-1,-1):
        i,d=st[k]
        cands=[d+120*m for m in range(-3,4)]
        tru=min(cands,key=lambda x:abs(x-prev)) if out else d
        out.append(((i-0.5)/fps,tru)); prev=tru
    return sorted(out), (st[last][0]+0.5)/fps
res={}
for name,(f0,f1) in {"coast":(354,392),"brake":(561,600),"low":(771,818)}.items():
    r=track(f0,f1); fps=r["fps"]
    print("==",name,"ellipse",[round(x) for x in r["ellipse"]])
    print(" raw:"," ".join("%d:%+d/%.2f"%(i,d,c) for i,d,c in r["steps"]))
    res[name]=r["steps"]
json.dump({k:[list(map(float,s)) for s in v] for k,v in res.items()},open("/private/tmp/claude-501/-Users-USER-blink-ota-esp8266-v36/4ccccbbb-9307-4e71-804f-1160f86304e6/scratchpad/steps44.json","w"))
