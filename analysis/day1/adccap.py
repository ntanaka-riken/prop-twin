import serial,time,json,sys
pre_cmd, wait, cap, out = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
s=serial.Serial('/dev/cu.usbserial-DN05I0TZ',115200,timeout=0.2); s.reset_input_buffer()
def cmd(c,w):
    s.write((c+"\n").encode()); s.flush(); t=time.time()+w; o=[]
    while time.time()<t:
        l=s.readline().decode(errors='replace').strip()
        if l and not l.startswith('[HB]'): o.append(l)
    return o
print(cmd(pre_cmd,wait))
lines=cmd(cap,4.5)
print([l for l in lines if l.startswith(("ADC cap","ACK","ERR"))])
data=[int(x) for l in lines if l.startswith("ADC ") and not l.startswith(("ADC cap","ADC end")) for x in l[4:].split(",")]
json.dump({"hdr":[l for l in lines if l.startswith("ADC cap")],"data":data},open(out,"w")); print("samples",len(data)); s.close()
