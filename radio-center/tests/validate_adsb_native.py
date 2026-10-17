import numpy as np,subprocess,pathlib,time
# Publicly documented ADS-B example frames; artificial baseband, no RF transmission.
frames=['8D40621D58C382D690C8AC2863A7','8D40621D58C386435CC412692AD6']
rate=2400000;length=240000;t=np.arange(length)/rate;v=np.zeros(length)
for i in range(16):
 start=.002+i*.005+((i%5)/5)/rate
 pulses=[start+x*1e-6 for x in (0,1,3.5,4.5)]
 bits=''.join(f'{b:08b}' for b in bytes.fromhex(frames[i%2]))
 pulses += [start+(8+j+(0 if bit=='1' else .5))*1e-6 for j,bit in enumerate(bits)]
 for p in pulses:
  a=int(np.floor(p*rate));b=int(np.ceil((p+.5e-6)*rate))
  for k in range(a,b):
   if 0<=k<length:v[k]+=max(0,min((k+1)/rate,p+.5e-6)-max(k/rate,p))*rate
rng=np.random.default_rng(42);iq=np.zeros((length,2));iq[:,0]=127+110*v+rng.normal(0,.3,length);iq[:,1]=127+rng.normal(0,.3,length);path=pathlib.Path('/tmp/adsb-synthetic-example.uc8');np.tile(np.clip(iq,0,255).astype('uint8'),(40,1)).tofile(path)
p=subprocess.Popen(['/usr/bin/dump1090-fa','--ifile',str(path),'--iformat','UC8','--raw','--no-fix','--throttle'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
time.sleep(.8);p.terminate();stdout,stderr=p.communicate(timeout=10)
found=[line for line in stdout.upper().splitlines() if '8D40621D' in line];print('Native decoder synthetic valid example frames:',len(found));print('Controlled exit:',p.returncode);assert p.returncode==0 and found
