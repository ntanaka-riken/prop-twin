import sys, numpy as np, json
sys.path.insert(0,".")
import identify as idf
V="~/Downloads/IMG_5742.MOV"
r=idf.video_track(V,(520,640),(660,740),xlim=(380,1120),ylim=880)
fps=r["fps"]; st=[(i,d) for i,d,c in r["steps"] if i>=668]
# unwrap: walk back from the stop; true step = apparent - 120k, continuous & monotonic
out=[]; prev=0.0
for i,d in reversed(st):
    cands=[d-120*k for k in range(0,4)]
    tru=min(cands,key=lambda x:abs(x-prev)) if prev<-5 or d<0 else d
    if abs(tru)<=1.5: tru=0.0
    out.append((i,tru)); prev=tru if tru!=0 else prev*0
out=sorted(out)
omega=[((i-0.5)/fps, -np.deg2rad(t)*fps) for i,t in out if t!=0]
for (t,w),(i,d) in zip(omega,[x for x in out if x[1]!=0]): print("%.3f  %6.1f deg/frame  w=%6.1f rad/s"%(t,d,w))
stop=[ (i-0.5)/fps for i,t in out if t==0 and (i-0.5)/fps>11.5][0]
host=json.load(open("data/sustain20_hostlog.json"))
tx=[e[0] for e in host if e[1]=="tx"]; led=[7.870,10.888,18.842]
off=float(np.mean([l-t for l,t in zip(led,tx)]))
m=dict(source="IMG_5742.MOV",fps=fps,led_flash_t=led,host_tx_t=tx,video_minus_host=off,
       f_full=50.30,t_full=led[0],t_20=led[1],t_off=led[2],t_stop=stop,video_omega_20pct=omega)
json.dump(m,open("data/IMG_5742_measured.json","w"),indent=1)
print("stop at %.3f s; offset video-host %.3f s"%(stop,off))
