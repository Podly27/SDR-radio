#!/usr/bin/python3
import collections,datetime,json,os,re,selectors,signal,sqlite3,subprocess,time
from pathlib import Path
from station_common import load as station_settings
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
import aprslib
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
PACKET=re.compile(r'^\[\d+(?:\.\d+)?\]\s*([^ >]+>[^:]+:.*)$')
def connect(name='aprs'):
 db=sqlite3.connect(DATA/(name+'.sqlite'),timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS packets(id INTEGER PRIMARY KEY,received TEXT NOT NULL,source TEXT NOT NULL,raw TEXT NOT NULL,payload TEXT NOT NULL,latitude REAL,longitude REAL,map_key TEXT NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS packets_map ON packets(map_key,id)');return db

def store(db,raw,radio=None):
 try:p=aprslib.parse(raw)
 except (aprslib.ParseError,aprslib.UnknownFormat,ValueError,IndexError):
  # Preserve packets whose APRS format is not supported, without invented positions.
  header,_,info=raw.partition(':');source,_,dest=header.partition('>')
  if not source or not dest:return False
  p={'from':source,'to':dest.split(',')[0],'path':dest.split(',')[1:],'comment':info,'parse_warning':'Nezpracovaný typ APRS; viz původní paket.'}
 if radio is not None:p['radio']=radio
 lat=p.get('latitude');lon=p.get('longitude')
 if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)) or not (-90<=lat<=90 and -180<=lon<=180):lat=lon=None
 key=str(p.get('object_name') or p.get('item_name') or p.get('from','')).strip()
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 db.execute('INSERT INTO packets(received,source,raw,payload,latitude,longitude,map_key) VALUES(?,?,?,?,?,?,?)',(now,p.get('from','?'),raw,json.dumps(p,ensure_ascii=False,default=str),lat,lon,key));db.commit();return True

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM packets WHERE received<?',(cutoff,));db.execute('DELETE FROM packets WHERE id<=(SELECT id FROM packets ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);db=connect();prune(db)
 config=DATA/'direwolf.conf';config.write_text(('ADEVICE stdin null\nARATE 24000\nACHANNELS 1\nCHANNEL 0\nMYCALL N0CALL\nMODEM 1200\nFIX_BITS 0\nAGWPORT 0\nKISSPORT 0\n').replace('MYCALL N0CALL','MYCALL '+station_settings()['callsign']))
 radio=subprocess.Popen(['/usr/bin/rtl_fm','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f','144.8M','-M','fm','-s','24000','-o','4','-g',str(SDR_GAIN),'-l','0','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 decoder=subprocess.Popen(['/usr/bin/stdbuf','-oL','-eL','/usr/bin/direwolf','-c',str(config),'-r','24000','-n','1','-b','16','-t','0','-'],stdin=radio.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 radio.stdout.close();stopping=False
 def stop(*_):
  global stopping
  stopping=True
  for p in (radio,decoder):
   if p.poll() is None:p.terminate()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 logs=collections.deque(maxlen=15);count=0;last=None;cleaned=time.monotonic();selector=selectors.DefaultSelector();buffers={}
 for stream in (radio.stderr,decoder.stdout,decoder.stderr):
  os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);buffers[stream.fileno()]=b''
 try:
  while selector.get_map() and not stopping:
   for key,_ in selector.select(timeout=1):
    fd=key.fileobj.fileno();chunk=os.read(fd,65536)
    if not chunk:selector.unregister(key.fileobj);continue
    buffers[fd]+=chunk
    while b'\n' in buffers[fd]:
     raw,buffers[fd]=buffers[fd].split(b'\n',1);line=raw.decode('utf-8',errors='replace').strip();match=PACKET.match(line)
     if match:
      if store(db,match[1]):count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
     elif line:logs.append(line[:1000]);print(line,flush=True)
   if time.monotonic()-cleaned>60:prune(db);cleaned=time.monotonic()
   state={'updated':time.time(),'frequency':144800000,'session_count':count,'last_received':last,'logs':list(logs)}
   tmp=DATA/'aprs-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'aprs-state.json')
   if radio.poll() is not None or decoder.poll() is not None:
    if not stopping:raise RuntimeError('APRS receive pipeline exited unexpectedly')
 finally:
  stop()
  for p in (radio,decoder):
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  db.close()
