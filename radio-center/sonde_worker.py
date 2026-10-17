#!/usr/bin/python3
"""Single-channel local radiosonde receiver using the installed RS decoders."""
import collections,datetime,hashlib,json,math,os,selectors,signal,sqlite3,subprocess,time
from pathlib import Path
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
TYPES={'RS41':('rs41mod',48000,['--ptu2']),'DFM':('dfm09mod',48000,['--ptu']),'DFM17':('dfm09mod',48000,['-i','--ptu']),'M10':('m10mod',76800,['--ptu']),'M20':('m20mod',76800,['--ptu']),'MTS01':('mts01mod',48000,[])}
DEFAULT={'type':'RS41','frequency':401500000}
def validate_config(kind,frequency):
 if kind not in TYPES or isinstance(frequency,bool) or not isinstance(frequency,int) or not 400000000<=frequency<=406000000:raise ValueError('Vyber podporovaný typ a frekvenci 400–406 MHz')
 return {'type':kind,'frequency':frequency}
def load_config():
 try:c=json.loads((DATA/'sonde-tuning.json').read_text())
 except FileNotFoundError:return DEFAULT.copy()
 return validate_config(c['type'],c['frequency'])
def connect():
 db=sqlite3.connect(DATA/'sonde.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY,received TEXT NOT NULL,sonde TEXT NOT NULL,type TEXT NOT NULL,frame TEXT NOT NULL,frequency INTEGER NOT NULL,lat REAL,lon REAL,alt REAL,temperature REAL,humidity REAL,pressure REAL,speed REAL,vertical REAL,heading REAL,payload TEXT NOT NULL,fingerprint TEXT NOT NULL UNIQUE)')
 db.execute('CREATE INDEX IF NOT EXISTS telemetry_sonde ON telemetry(sonde,id)');return db

def value(p,key,lo,hi):
 v=p.get(key)
 return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and lo<=v<=hi else None

def normalize(payload):
 if not isinstance(payload,dict) or not payload.get('id'):return None
 serial=str(payload['id']).strip()
 if not serial or len(serial)>64:return None
 lat=value(payload,'lat',-90,90);lon=value(payload,'lon',-180,180);sats=payload.get('sats')
 if lat is None or lon is None or (lat==0 and lon==0) or (isinstance(sats,(int,float)) and sats<4):lat=lon=None
 return dict(sonde=serial,type=str(payload.get('subtype') or payload.get('type') or 'SONDE')[:64],frame=str(payload.get('frame',''))[:32],lat=lat,lon=lon,alt=value(payload,'alt',-500,60000),temperature=value(payload,'temp',-120,70),humidity=value(payload,'humidity',0,100),pressure=value(payload,'pressure',.01,1200),speed=value(payload,'vel_h',0,500),vertical=value(payload,'vel_v',-200,200),heading=value(payload,'heading',0,360))

def store(db,payload,frequency):
 # Non-finite measurements must not break strict JSON consumers in the browser.
 payload=json.loads(json.dumps(payload),parse_constant=lambda _:None)
 p=normalize(payload)
 if p is None:return False
 now=datetime.datetime.now(datetime.timezone.utc).isoformat();raw=json.dumps(payload,ensure_ascii=False,sort_keys=True)
 if p['frame']:key=p['sonde']+'|'+p['frame']+'|'+str(payload.get('datetime') or now[:10])
 else:key=p['sonde']+'|'+hashlib.sha256(raw.encode()).hexdigest()
 cursor=db.execute('INSERT OR IGNORE INTO telemetry(received,sonde,type,frame,frequency,lat,lon,alt,temperature,humidity,pressure,speed,vertical,heading,payload,fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(now,p['sonde'],p['type'],p['frame'],frequency,p['lat'],p['lon'],p['alt'],p['temperature'],p['humidity'],p['pressure'],p['speed'],p['vertical'],p['heading'],raw,key));db.commit();return cursor.rowcount==1

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM telemetry WHERE received<?',(cutoff,));db.execute('DELETE FROM telemetry WHERE id<=(SELECT id FROM telemetry ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);cfg=load_config();executable,rate,options=TYPES[cfg['type']];db=connect();prune(db)
 radio=subprocess.Popen(['/usr/bin/rtl_fm','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(cfg['frequency']),'-M','raw','-s',str(rate),'-g',str(SDR_GAIN),'-l','0','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 decoder=subprocess.Popen(['/usr/bin/stdbuf','-oL','-eL','/usr/bin/'+executable,'-',str(rate),'16','--IQ','0',*options,'--json'],stdin=radio.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 radio.stdout.close();stopping=False
 def stop(*_):
  global stopping
  stopping=True
  for p in (radio,decoder):
   if p.poll() is None:p.terminate()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 logs=collections.deque(maxlen=15);count=0;last=None;cleaned=time.monotonic();selector=selectors.DefaultSelector();buffers={}
 for stream,kind in [(radio.stderr,'log'),(decoder.stdout,'data'),(decoder.stderr,'log')]:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,kind);buffers[stream.fileno()]=b''
 try:
  while selector.get_map() and not stopping:
   for key,_ in selector.select(timeout=1):
    fd=key.fileobj.fileno();chunk=os.read(fd,65536)
    if not chunk:selector.unregister(key.fileobj);continue
    buffers[fd]+=chunk
    while b'\n' in buffers[fd]:
     raw,buffers[fd]=buffers[fd].split(b'\n',1);line=raw.decode('utf-8',errors='replace').strip()
     if key.data=='data' and line.startswith('{'):
      try:
       if store(db,json.loads(line),cfg['frequency']):count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
      except (ValueError,TypeError):logs.append('Neplatná telemetrie dekodéru')
     elif line:logs.append(line[:1000]);print(line,flush=True)
   if time.monotonic()-cleaned>60:prune(db);cleaned=time.monotonic()
   state={'updated':time.time(),'type':cfg['type'],'frequency':cfg['frequency'],'sample_rate':rate,'session_count':count,'last_received':last,'logs':list(logs)}
   tmp=DATA/'sonde-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'sonde-state.json')
   if radio.poll() is not None or decoder.poll() is not None:
    if not stopping:raise RuntimeError('Radiosonde receive pipeline exited')
 finally:
  stop()
  for p in (radio,decoder):
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  db.close()
