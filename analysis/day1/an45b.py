import sys, json, numpy as np; sys.path.insert(0,".")
import identify as idf
V="~/Downloads/IMG_5745.MOV"; OFF=9.227
h=json.load(open("data/JK_coin_hostlog.json")); tx=[(x[0],x[2]) for x in h if x[1]=="tx"]
stops=[(t+OFF,c) for t,c in tx if c in ("dcm:off","dcm:brake") and [x for x in tx if x[0]<t][-1][1]=="dcm:speed 255"]
fps=29.9992; res=[]
for t,c in stops:
    f0=int(t*fps); f1=int((t+3.6)*fps)
    r=idf.video_track(V,(int((t-1.2)*fps),int((t-0.2)*fps)),(f0,f1),xlim=(480,1420),ylim=840)
    st=[(i,d) for i,d,cc in r["steps"]]
    nz=[k for k,(i,d) in enumerate(st) if abs(d)>1]
    last=nz[-1]
    print("== %s cmd %.3f  ellipse %s"%(c,t,[round(x) for x in r["ellipse"]]))
    print("   tail:"," ".join("%d:%+d"%(i,d) for i,d in st[max(0,last-14):last+3]))
    res.append(dict(cmd=c,t_cmd=t,last_moving_frame=st[last][0],t_stop=(st[last][0]+0.5)/fps,steps=[[int(i),int(d)] for i,d in st]))
    print("   stop %.3f  duration %.3f"%(res[-1]["t_stop"],res[-1]["t_stop"]-t))
json.dump(res,open("/private/tmp/claude-501/-Users-USER-blink-ota-esp8266-v36/4ccccbbb-9307-4e71-804f-1160f86304e6/scratchpad/stops45.json","w"))
