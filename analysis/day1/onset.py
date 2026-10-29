import cv2, numpy as np, json, sys
V,host,x0,x1,y0,y1=sys.argv[1],sys.argv[2],*map(int,sys.argv[3:7])
v=cv2.VideoCapture(V); fps=v.get(5); prev=None; d=[]
while True:
    ok,f=v.read()
    if not ok: break
    g=cv2.cvtColor(f[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY).astype(float)
    d.append(0 if prev is None else np.abs(g-prev).mean()); prev=g
d=np.array(d)
h=json.load(open(host)); st=[x[0] for x in h if x[1]=="tx" and x[2]=="dcm:speed 255"]
return_=[]
for guess in [float(a) for a in sys.argv[7].split(",")]:
    out=[]
    for t in st:
        k0=int((t+guess-0.7)*fps); k1=int((t+guess+0.7)*fps)
        base=np.median(d[k0:k0+10]); noise=np.std(d[k0:k0+10])+0.2
        k=next((k for k in range(k0+10,k1) if d[k]>base+6*noise and d[k+1]>base+6*noise),None)
        out.append((t,(k-0.5)/fps if k else None, d[k:k+3].round(1).tolist() if k else None))
    offs=[o-t for t,o,_ in out if o]
    print("guess %.2f:"%guess, "  ".join("%.3f->%s"%(t,"%.3f"%o if o else "-") for t,o,_ in out))
    print("   offsets",np.round(offs,3),"median %.3f sd %.3f"%(np.median(offs),np.std(offs)))
