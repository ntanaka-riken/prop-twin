import cv2, numpy as np, sys, json
V,host=sys.argv[1],sys.argv[2]
v=cv2.VideoCapture(V); fps=v.get(5)
cx,cy,r=(int(sys.argv[3]),int(sys.argv[4]),45) if len(sys.argv)>4 else (int(478/.4),int(347/.4),45)
tr=[]
while True:
    ok,f=v.read()
    if not ok: break
    tr.append(f[cy-r:cy+r,cx-r:cx+r].max(axis=2).astype(float).mean())
tr=np.array(tr); base=np.median(tr); thr=base+0.5*(tr.max()-base)
on=tr>thr; e=np.flatnonzero(np.diff(on.astype(int))==1)+1
ends=np.flatnonzero(np.diff(on.astype(int))==-1)+1
print("base %.0f max %.0f n flashes %d"%(base,tr.max(),len(e)))
h=json.load(open(host)); tx=[(x[0],x[2]) for x in h if x[1]=="tx"]
ts=[(k-0.5)/fps for k in e]
for k,(t,(th,c)) in enumerate(zip(ts,tx)): print("flash %.3f  len %d fr   host %.3f %-14s  diff %.3f"%(t,(ends[k]-e[k]) if k<len(ends) else -1,th,c,t-th))
