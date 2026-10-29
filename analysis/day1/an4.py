import sys, numpy as np, cv2, json
sys.path.insert(0,".")
import identify as idf
V="~/Downloads/IMG_5742.MOV"
r=idf.video_track(V,(520,640),(640,760),xlim=(380,1120),ylim=880)
print("fps %.3f ellipse"%r["fps"],[round(x) for x in r["ellipse"]],"onset_t %.3f stop_t"%r["onset_t"],r["stop_t"])
for i,d,c in r["steps"]: print(i,"t=%.3f"%((i-0.5)/r["fps"]),"d=%+d"%d,"c=%.3f"%c)
