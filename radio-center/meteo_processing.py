#!/usr/bin/python3
"""Finish SatDump products after RF release; replay bounded diagnostic clips."""
import datetime,json,os,re,subprocess,time,uuid
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
import meteo_common as common

def enqueue(job):
 folder=common.DATA/'meteo-process';folder.mkdir(exist_ok=True)
 common.atomic('meteo-process/'+uuid.uuid4().hex+'.json',job)

def enqueue_cadu(output,config,capture):
 files=[p for p in Path(output).rglob('*.cadu') if p.stat().st_size>=1024]
 for p in files:enqueue({'kind':'cadu','input':str(p),'output':str(p.parent/'products'),'config':config,'capture':capture,'created':time.time()})
 return bool(files)

def safe_path(value):
 path=Path(value).resolve()
 if not any(path.is_relative_to((common.DATA/name).resolve()) for name in ('meteo-work','meteo-diagnostics')):raise ValueError('Cesta mimo pracovní data Meteoru')
 return path

def native_decode(source,output,c,level='cadu',timestamp=None):
 output.mkdir(parents=True,exist_ok=True)
 cmd=['/usr/bin/satdump','meteor_m2-x_lrpt'+('_80k' if c['symbolrate']==80000 else ''),level,str(source),str(output),'--satellite_number',c['satellite'],'--rs_usecheck','true','--fill_missing','false']
 if c['symbolrate']==72000:cmd+=['--pll_bw',str(common.LRPT_PLL_BW)]
 if level=='baseband':cmd+=['--samplerate','256000','--baseband_format','cs16','--dc_block','--frequency',str(c['frequency'])]
 if timestamp is not None:cmd+=['--start_timestamp',str(timestamp)]
 tle=common.DATA/'meteo-satdump/tle.txt'
 if tle.exists():cmd+=['--tle_override',str(tle)]
 log=output/'decode.log';started=time.monotonic()
 with log.open('wb') as fd:
  try:r=subprocess.run(cmd,cwd=common.DATA/'meteo-satdump',stdout=fd,stderr=subprocess.STDOUT,timeout=150,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
  except subprocess.TimeoutExpired:return {'error':'Offline dekódování překročilo 150 s','seconds':time.monotonic()-started}
 text=log.read_text(errors='replace');snr=[float(v) for v in re.findall(r'Peak SNR:\s*([-\d.]+)',text)];bers=[float(v) for v in re.findall(r'BER\s*:\s*([-\d.]+)',text)]
 cadu=sum(p.stat().st_size for p in output.rglob('*.cadu'))
 return {'returncode':r.returncode,'seconds':round(time.monotonic()-started,2),'cadu_bytes':cadu,'peak_snr':max(snr,default=None),'best_ber':min(bers,default=None),'synchronized':cadu>=1024 or bool(re.search(r'(?:Viterbi|Deframer)\s*:\s*SYNC\b',text)),'log':str(log)}

def channelize(source,target,frequency,samplerate=2048000,center=137500000):
 # Each clip is at most 12 s; convert in bounded 1-second chunks, preserving
 # mixer phase. Keep filter context at chunk boundaries to avoid false gaps.
 count=source.stat().st_size//2
 raw=np.memmap(source,dtype=np.uint8,mode='r',shape=(count,2))
 block=samplerate;overlap=256
 with target.open('wb') as fd:
  for start in range(0,count,block):
   left=max(0,start-overlap);right=min(count,start+block+overlap)
   a=raw[left:right].astype(np.float32);z=(a[:,0]-127.5+1j*(a[:,1]-127.5))/128
   phase=np.arange(left,right,dtype=np.float64)*(2*np.pi*(center-frequency)/samplerate)
   z*=np.exp(1j*phase).astype(np.complex64)
   y=resample_poly(z,1,8);offset=(start-left)//8;length=(min(count,start+block)-start)//8;y=y[offset:offset+length]
   out=np.empty((len(y),2),dtype='<i2');out[:,0]=np.clip(y.real*32767,-32768,32767);out[:,1]=np.clip(y.imag*32767,-32768,32767);fd.write(out.tobytes())
 del raw

def process(job):
 from meteo_worker import import_images
 c=common.validate(job['config']);source=safe_path(job['input']);output=safe_path(job['output']);capture=job['capture']
 report={**job,'started':time.time(),'results':[],'images':0}
 if job['kind']=='cadu':
  result=native_decode(source,output,c);report['results'].append(result)
  if result.get('returncode')==0:report['images']=import_images(output,c,capture)
 else:
  for frequency in (137900000,137100000):
   channel=source.with_name(source.stem+'-'+str(frequency)+'.cs16')
   channelize(source,channel,frequency)
   try:
    for rate in (72000,80000):
     selected={**c,'frequency':frequency,'symbolrate':rate};dst=output/(str(frequency)+'-'+str(rate))
     result=native_decode(channel,dst,selected,'baseband',job['created']);result.update(frequency=frequency,symbolrate=rate)
     if result.get('returncode')==0:result['images']=import_images(dst,selected,capture+'-'+str(frequency)+'-'+str(rate));report['images']+=result.get('images',0)
     report['results'].append(result)
   finally:channel.unlink(missing_ok=True) # Derived copy only; original IQ remains.
 report['finished']=time.time();return report

def main():
 queue=common.DATA/'meteo-process';queue.mkdir(exist_ok=True);reports=common.DATA/'meteo-reports';reports.mkdir(exist_ok=True)
 for path in sorted(queue.glob('*.json')):
  try:
   job=json.loads(path.read_text());report=process(job)
  except Exception as exc:report={'job':str(path),'error':str(exc),'finished':time.time()}
  common.atomic('meteo-reports/'+path.name,report);path.unlink();summarize();print(json.dumps(report,ensure_ascii=False),flush=True)

def summarize():
 try:plan=json.loads((common.DATA/'meteo-diagnostic-plan.json').read_text())
 except (OSError,ValueError):return
 groups={};completed=0;errors=0
 for path in (common.DATA/'meteo-reports').glob('*.json'):
  try:report=json.loads(path.read_text())
  except (OSError,ValueError):continue
  if report.get('kind')!='iq' or report.get('created',0)<plan.get('created',0):continue
  completed+=1
  for result in report.get('results',[]):
   key=(result['frequency'],result['symbolrate'],report['gain'])
   row=groups.setdefault(key,{'frequency':key[0],'symbolrate':key[1],'gain':key[2],'clips':0,'cadu_frames':0,'images':0,'maximum_rf_db':None})
   row['clips']+=1;row['cadu_frames']+=result.get('cadu_bytes',0)//1024;row['images']+=result.get('images',0)
   rf=report.get('rf',{}).get(str(key[0]),{}).get('band_to_noise_db')
   if rf is not None:row['maximum_rf_db']=max(row['maximum_rf_db'] if row['maximum_rf_db'] is not None else rf,rf)
   if result.get('returncode')!=0:errors+=1
 rows=sorted(groups.values(),key=lambda r:(r['images'],r['cadu_frames']),reverse=True)
 images=sum(r['images'] for r in rows);frames=sum(r['cadu_frames'] for r in rows)
 message='Čeká na první diagnostický záznam.' if not completed else 'Zatím žádné potvrzené rámce LRPT; porovnávám RF signál, frekvenci a režimy.'
 if frames:message='Zachyceny rámce CADU; probíhá kontrola převodu na obrázky.'
 if images:message='Úspěšné dekódování: '+str(images)+' snímků z reálných diagnostických záznamů.'
 update=None
 # Only proven image decoding may alter the next pass. Never choose a setting
 # from RSSI alone, and never overwrite a user's intervening profile changes.
 if images and time.time()<plan['expires']:
  winner=rows[0];current=common.load_config();baseline=plan.get('baseline',{})
  if current['satellite']==plan['satellite'] and all(k in baseline and current[k]==baseline[k] for k in ('frequency','symbolrate')):
   if (current['frequency'],current['symbolrate'])!=(winner['frequency'],winner['symbolrate']):
    current.update(frequency=winner['frequency'],symbolrate=winner['symbolrate']);common.atomic('meteo-config.json',current);update={'frequency':winner['frequency'],'symbolrate':winner['symbolrate'],'reason':'Ověřeno skutečně dekódovanými obrázky; použije se pro další příjem.'}
 common.atomic('meteo-diagnostic-summary.json',{'updated':time.time(),'completed_clips':completed,'decoder_errors':errors,'cadu_frames':frames,'images':images,'message':message,'comparisons':rows,'automatic_setting_change':update})
if __name__=='__main__':main()
