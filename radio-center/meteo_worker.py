#!/usr/bin/python3
"""Headless SatDump capture and bounded gallery import; no custom LRPT decoder."""
import collections,datetime,json,os,re,selectors,shutil,signal,subprocess,time,uuid
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen
from PIL import Image
import numpy as np
import meteo_common as common
from sdr_calibration import SDR_PPM,SDR_DEVICE
ANSI=re.compile(r'\x1b\[[0-9;]*m')
def command(c,output,duration):
 pipeline='meteor_m2-x_lrpt'+('_80k' if c['symbolrate']==80000 else '')
 return ['/usr/bin/satdump','live',pipeline,str(output),'--source','rtlsdr',*(['--source_id',SDR_DEVICE] if SDR_DEVICE!='0' else []),'--samplerate','1000000','--frequency',str(c['frequency']),'--gain',str(c['gain']),'--ppm_correction',str(SDR_PPM),'--dc_block','--satellite_number',c['satellite'],'--timeout',str(duration),'--http_server','127.0.0.1:8092','--fill_missing','false','--rs_usecheck','true','--tle_override',str(common.DATA/'meteo-satdump'/'tle.txt')]

def import_images(output,c,capture):
 directory=common.DATA/'meteo-images';directory.mkdir(parents=True,exist_ok=True);count=0
 # Import instrument products only, not icons/maps or an empty generated dataset.
 for source in sorted(Path(output).rglob('*.png')):
  if not any('msu' in part.lower() for part in source.relative_to(output).parts[:-1]):continue
  if source.stat().st_size>40*1024**2:continue
  try:
   with Image.open(source) as image:
    if image.width<64 or image.height<8:continue
    width,height=image.size;image.thumbnail((1600,6000),Image.Resampling.NEAREST);image.load();a=np.asarray(image)
    if a.dtype==np.uint16 or image.mode in ('I','I;16'):
     values=a[a>0]
     low,high=np.percentile(values,[1,99]) if values.size else (0,1)
     a=(np.clip((a.astype(np.float32)-low)/max(1,high-low),0,1)*255).astype(np.uint8);image=Image.fromarray(a)
    image=image.convert('RGB');image.thumbnail((1600,12000));name=uuid.uuid4().hex;preview=name+'.png';original=name+'-original.png';image.save(directory/preview);shutil.copyfile(source,directory/original)
   received=datetime.datetime.now(datetime.timezone.utc).isoformat()
   with closing(common.connect()) as db:
    db.execute('INSERT INTO images(received,capture,filename,original,label,satellite,frequency,width,height) VALUES(?,?,?,?,?,?,?,?,?)',(received,capture,preview,original,str(source.relative_to(output)),c['satellite'],c['frequency'],width,height));db.commit()
   count+=1
  except (OSError,ValueError) as exc:print('Image import:',source.name,exc,flush=True)
 common.prune();return count

def metrics():
 try:
  with urlopen('http://127.0.0.1:8092/api',timeout=.5) as response:return json.loads(response.read(65536))
 except (OSError,ValueError):return None

def main():
 common.DATA.mkdir(parents=True,exist_ok=True);job=json.loads((common.DATA/'meteo-run.json').read_text());c=common.validate(job['config']);duration=int(common.number(job['duration'],1,900));capture=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8];output=common.DATA/'meteo-work'/capture;output.mkdir(parents=True);logs=collections.deque(maxlen=25);stopping=False;process=None;last=0;status={};count=0;error=None
 def stop(*_):
  nonlocal stopping
  stopping=True
  if process and process.poll() is None:process.send_signal(signal.SIGINT)
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  if shutil.disk_usage(common.DATA).free<600*1024**2:raise RuntimeError('Pro příjem zbývá méně než 600 MiB volného místa')
  settings=common.DATA/'meteo-satdump';settings.mkdir(parents=True,exist_ok=True)
  tle,_=common.read_tle(c['satellite']);(settings/'tle.txt').write_text('\n'.join(tle[k] for k in ('name','line1','line2'))+'\n')
  process=subprocess.Popen(command(c,output,duration),cwd=settings,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0);selector=selectors.DefaultSelector();os.set_blocking(process.stdout.fileno(),False);selector.register(process.stdout,selectors.EVENT_READ);buffer=b'';stop_at=None
  while process.poll() is None:
   for key,_ in selector.select(timeout=.5):
    chunk=os.read(key.fileobj.fileno(),16384)
    if not chunk:selector.unregister(key.fileobj);continue
    buffer+=chunk
    while b'\n' in buffer:
     line,buffer=buffer.split(b'\n',1);text=ANSI.sub('',line.decode(errors='replace')).strip()
     if text:logs.append(text[:1200]);print(text,flush=True)
    if len(buffer)>65536:buffer=buffer[-4096:]
   if stopping:
    if stop_at is None:stop_at=time.monotonic()
    elif time.monotonic()-stop_at>25:process.kill();error='SatDump se nezastavil v limitu'
   if time.monotonic()-last>2:
    status={'updated':time.time(),'frequency':c['frequency'],'satellite':c['satellite'],'symbolrate':c['symbolrate'],'capture':capture,'phase':'receiving','metrics':metrics(),'session_count':0,'logs':list(logs)};common.atomic('meteo-rx-state.json',status);last=time.monotonic()
  code=process.wait()
  if code and not stopping:raise RuntimeError('SatDump skončil s kódem '+str(code))
 except Exception as exc:error=str(exc);raise
 finally:
  if process and process.poll() is None:
   process.send_signal(signal.SIGINT)
   try:process.wait(timeout=20)
   except subprocess.TimeoutExpired:process.kill();process.wait()
  status.update(updated=time.time(),phase='importing',logs=list(logs));common.atomic('meteo-rx-state.json',status)
  try:count=import_images(output,c,capture)
  except Exception as exc:error='Uložení snímků: '+str(exc)
  status.update(updated=time.time(),phase='stopped',session_count=count,error=error,logs=list(logs));common.atomic('meteo-rx-state.json',status)
  # Captures with no decoded imagery must not accumulate raw data indefinitely.
  if not count:shutil.rmtree(output,ignore_errors=True)
if __name__=='__main__':main()
