import cv2, numpy as np, sys, json, scipy.signal as sg
V,host,cx,cy=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]); r=14
v=cv2.VideoCapture(V); fps=v.get(5); tr=[]
while True:
    ok,f=v.read()
    if not ok: break
    p=f[cy-r:cy+r,cx-r:cx+r].astype(float); tr.append([p[...,2].mean(),p[...,1].mean(),p[...,0].mean()])
tr=np.array(tr); Y=tr.mean(axis=1)
base=sg.medfilt(Y,21); d=Y-base
print("d percentiles",np.percentile(d,[50,90,99,99.9]).round(1),"max %.1f"%d.max())
thr=0.5*np.percentile(d,99.7)
on=d>thr; e=np.flatnonzero(np.diff(on.astype(int))==1)+1; x=np.flatnonzero(np.diff(on.astype(int))==-1)+1
pulses=[(a,b-a) for a,b in zip(e,x[x>e[0]][:len(e)])]
print("pulses (frame,len,peak):",[(int(a),int(l),round(float(d[a:a+l].max()),1)) for a,l in pulses])
h=json.load(open(host)); tx=[x[0] for x in h if x[1]=="tx"]
nexp=0.1*fps; ts=[(a-0.5)/fps for a,l in pulses if nexp-2<=l<=nexp+2]
# best offset: match flash times to host tx with offset search
best=None
for off in np.arange(0,20,0.005):
    m=[min(abs(t-(x+off)) for t in ts) for x in tx]; sc=sum(min(mm,0.1) for mm in m)
    if best is None or sc<best[0]: best=(sc,off,m)
sc,off,m=best; print("offset %.3f  matched %d/%d"%(off,sum(mm<0.04 for mm in m),len(tx)))
res=[]
for x,mm in zip(tx,m):
    near=min(ts,key=lambda t:abs(t-(x+off))); res.append((x,near if mm<0.04 else None))
print("  ".join("%.3f->%s"%(x,("%.3f"%n) if n else "--") for x,n in res))
good=[n-x for x,n in res if n]; print("offset mean %.4f sd %.4f n=%d"%(np.mean(good),np.std(good),len(good)))
