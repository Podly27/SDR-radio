#!/usr/bin/python3
"""Local multichannel dumpvdl2 receiver with durable decoded JSON history."""
import collections,datetime,json,os,selectors,signal,sqlite3,subprocess,time
from pathlib import Path
from station_common import load as station_settings
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
CHANNELS=(136725000,136775000,136875000,136975000)
def connect():
 db=sqlite3.connect(DATA/'vdl2.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS frames(id INTEGER PRIMARY KEY,received TEXT NOT NULL,frequency INTEGER NOT NULL,source TEXT NOT NULL,destination TEXT NOT NULL,aircraft TEXT NOT NULL,registration TEXT NOT NULL,flight TEXT NOT NULL,message TEXT NOT NULL,kind TEXT NOT NULL,snr REAL,payload TEXT NOT NULL)');return db

def summarize(payload):
 if not isinstance(payload,dict):return None
 v=payload.get('vdl2');a=v.get('avlc') if isinstance(v,dict) else None
 if not isinstance(a,dict):return None
 src=a.get('src') or {};dst=a.get('dst') or {};acars=a.get('acars') or {}
 aircraft=next((str(x.get('addr','')) for x in (src,dst) if x.get('type')=='Aircraft'),'')
 registration=str(acars.get('reg',acars.get('registration','')));flight=str(acars.get('flight',''))
 message=str(acars.get('msg_text',acars.get('text','')))
 kind='ACARS' if acars else 'XID' if 'xid' in a else 'X.25 / ATN' if 'x25' in a else 'AVLC '+str(a.get('frame_type',''))+' '+str(a.get('cmd',''))
 signal_level=v.get('sig_level');noise=v.get('noise_level')
 snr=signal_level-noise if isinstance(signal_level,(int,float)) and isinstance(noise,(int,float)) else None
 try:frequency=int(v['freq'])
 except (KeyError,ValueError,TypeError):return None
 return dict(frequency=frequency,source=str(src.get('addr','?')),destination=str(dst.get('addr','?')),aircraft=aircraft,registration=registration,flight=flight,message=message,kind=kind.strip(),snr=snr)

def store(db,payload):
 values=summarize(payload)
 if values is None:return False
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 db.execute('INSERT INTO frames(received,frequency,source,destination,aircraft,registration,flight,message,kind,snr,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(now,values['frequency'],values['source'],values['destination'],values['aircraft'],values['registration'],values['flight'],values['message'],values['kind'],values['snr'],json.dumps(payload,ensure_ascii=False)));db.commit();return True

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM frames WHERE received<?',(cutoff,));db.execute('DELETE FROM frames WHERE id<=(SELECT id FROM frames ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);db=connect();prune(db)
 command=['/usr/bin/stdbuf','-oL','-eL','/usr/bin/dumpvdl2','--rtlsdr',SDR_DEVICE,'--correction',str(SDR_PPM),'--gain',str(SDR_GAIN),'--oversample','10','--decode-fragments','--utc','--station-id',station_settings()['callsign'],'--output','decoded:json:file:path=-',*[str(f) for f in CHANNELS]]
 p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 stopping=False
 def stop(*_):
  global stopping
  stopping=True
  if p.poll() is None:p.send_signal(signal.SIGINT)
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 selector=selectors.DefaultSelector();buffers={};logs=collections.deque(maxlen=15);count=0;last=None;cleaned=time.monotonic()
 for stream,kind in [(p.stdout,'data'),(p.stderr,'log')]:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,kind);buffers[stream.fileno()]=b''
 try:
  while selector.get_map() and not stopping:
   for key,_ in selector.select(timeout=1):
    fd=key.fileobj.fileno();chunk=os.read(fd,65536)
    if not chunk:selector.unregister(key.fileobj);continue
    buffers[fd]+=chunk
    while b'\n' in buffers[fd]:
     raw,buffers[fd]=buffers[fd].split(b'\n',1);line=raw.decode('utf-8',errors='replace').strip()
     if not line:continue
     if key.data=='data':
      try:
       if store(db,json.loads(line)):count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
      except json.JSONDecodeError:logs.append(line[:1000])
     else:logs.append(line[:1000]);print(line,flush=True)
   if time.monotonic()-cleaned>60:prune(db);cleaned=time.monotonic()
   state={'updated':time.time(),'channels':CHANNELS,'session_count':count,'last_received':last,'logs':list(logs)}
   tmp=DATA/'vdl2-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'vdl2-state.json')
   if p.poll() is not None and not stopping:raise RuntimeError('VDL2 receiver exited')
 finally:
  stop()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
  db.close()
