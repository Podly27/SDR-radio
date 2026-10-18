#!/usr/bin/python3
"""One-night bounded RF experiment, sharing normal Meteor SDR ownership."""
import datetime,json,math,selectors,shutil,signal,subprocess,time
from pathlib import Path
import numpy as np
import meteo_common as common
from sdr_calibration import SDR_DEVICE,SDR_PPM
RATE=2048000
CENTER=137500000

def selected_pass():
 try:
  plan=json.loads((common.DATA/'meteo-diagnostic-plan.json').read_text());job=json.loads((common.DATA/'meteo-run.json').read_text());now=time.time()
  if now>plan['expires'] or not job.get('automatic') or job['config']['satellite']!=plan['satellite']:return None
  window=next((p for p in plan['passes'] if p['start']-15<=now<p['end']),None)
  return {'window':window,'job':job} if window else None
 except (OSError,ValueError,KeyError,TypeError):return None

def spectrum(path):
 raw=np.memmap(path,dtype=np.uint8,mode='r');size=32768;power=np.zeros(size);count=0;clip=0;points=0
 # Average separated windows across the whole clip, not merely its USB startup.
 for start in np.linspace(min(RATE*2,len(raw)//4),max(min(RATE*2,len(raw)//4),len(raw)-2*size),32,dtype=int):
  start-=start%2;a=np.asarray(raw[start:start+2*size]).reshape(-1,2)
  if len(a)!=size:continue
  clip+=int(np.count_nonzero((a<2)|(a>253)));points+=a.size
  z=(a[:,0].astype(np.float32)-127.5)+1j*(a[:,1].astype(np.float32)-127.5);z-=z.mean()
  power+=abs(np.fft.fftshift(np.fft.fft(z*np.hanning(size))))**2;count+=1
 power/=max(count,1);freq=np.fft.fftshift(np.fft.fftfreq(size,1/RATE))+CENTER
 channels={}
 for center in (137100000,137900000):
  delta=abs(freq-center);inside=(delta>2000)&(delta<70000);outside=(delta>130000)&(delta<220000)
  noise=float(np.median(power[outside]));ratio=float(np.mean(power[inside])/max(noise,1e-30))
  channels[str(center)]={'band_to_noise_db':round(10*math.log10(max(ratio,1e-30)),2),'note':'RF power estimate; not proof of LRPT or calibrated decoder SNR'}
 # Compact PSD supports later plotting and checking narrowband interference.
 stride=8;psd=10*np.log10(np.maximum(power.reshape(-1,stride).mean(axis=1),1e-30))
 return {'channels':channels,'clipped_percent':round(100*clip/max(1,points),4),'frequencies_hz':freq.reshape(-1,stride).mean(axis=1).tolist(),'power_db_relative':psd.round(2).tolist()}

def run_pass(selected):
 from meteo_processing import enqueue
 job=selected['job'];c=common.validate(job['config']);window=selected['window'];capture=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-diagnostic';folder=common.DATA/'meteo-diagnostics'/capture;folder.mkdir(parents=True)
 stopped=False;process=None;logs=[];records=[]
 def stop(*_):
  nonlocal stopped
  stopped=True
  if process and process.poll() is None:process.send_signal(signal.SIGINT)
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 def state(phase):
  common.atomic('meteo-rx-state.json',{'updated':time.time(),'frequency':c['frequency'],'satellite':c['satellite'],'symbolrate':c['symbolrate'],'capture':capture,'phase':phase,'diagnostic':True,'session_count':0,'metrics':None,'logs':logs[-25:],'error':None})
 try:
  settings=common.DATA/'meteo-satdump';settings.mkdir(exist_ok=True);tle,_=common.read_tle(c['satellite']);(settings/'tle.txt').write_text('\n'.join(tle[k] for k in ('name','line1','line2'))+'\n')
  fractions=(.14,.22,.30,.40,.48,.56,.66,.74,.82)
  for index,fraction in enumerate(fractions):
   at=window['start']+fraction*(window['end']-window['start']);gain=(40.2,29.7,49.6)[index%3]
   while not stopped and time.time()<at:
    state('diagnostic-waiting');time.sleep(min(2,max(.05,at-time.time())))
   if stopped or time.time()+14>=window['end']:break
   if shutil.disk_usage(common.DATA).free<2*1024**3:logs.append('Diagnostika zastavena: rezerva disku pod 2 GiB');break
   path=folder/('clip-%02d-gain%.1f.cu8'%(index,gain));started=time.time();command=['/usr/bin/rtl_sdr','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(CENTER),'-s',str(RATE),'-g',str(gain),'-n',str(RATE*12),str(path)]
   logs.append('IQ 137,5 MHz / 2,048 MS/s · obě frekvence · zisk '+str(gain)+' dB');state('diagnostic-capturing')
   with path.with_suffix('.log').open('wb') as fd:
    process=subprocess.Popen(command,stdout=fd,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+30
    while process.poll() is None and not stopped:
     if time.monotonic()>deadline:process.kill();logs.append('RTL-SDR překročil časový limit');break
     state('diagnostic-capturing');time.sleep(1)
    if stopped and process.poll() is None:process.send_signal(signal.SIGINT)
    process.wait(timeout=5)
   if path.exists() and path.stat().st_size>RATE*2:
    metrics=spectrum(path);record={'input':str(path),'gain':gain,'created':started,'samples':path.stat().st_size//2,'rf':metrics,'command':command,'returncode':process.returncode};records.append(record);common.atomic(str(path.relative_to(common.DATA))+'.json',record)
    enqueue({'kind':'iq','input':str(path),'output':str(folder/path.stem),'config':c,'capture':capture+'-'+str(index),'created':started,'gain':gain,'rf':metrics['channels']})
    logs.append('Uloženo '+str(round(path.stat().st_size/1024**2,1))+' MiB; čeká replay 137,1/137,9 MHz × 72k/80k');state('diagnostic-queued')
   if stopped:break
  while not stopped and time.time()<window['end']:
   state('diagnostic-waiting');time.sleep(2)
 finally:
  if process and process.poll() is None:
   process.kill();process.wait()
  common.atomic(str(folder.relative_to(common.DATA))+'/summary.json',{'capture':capture,'window':window,'config':c,'clips':records,'finished':time.time(),'stopped':stopped})
  state('stopped')
