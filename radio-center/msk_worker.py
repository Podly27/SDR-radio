#!/usr/bin/python3
import collections,datetime,json,os,re,selectors,signal,sqlite3,subprocess,time
from pathlib import Path
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
from ft_profiles import MSK_PROFILES,validate_msk_frequency
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
LINE=re.compile(r'^\*\*\*\s+(\d{6})\s+(-?\d+)\s+([+-]?[\d.]+)\s+(\d+)\s+&\s+(.+?)\s*$')
def connect():
 db=sqlite3.connect(DATA/'msk.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,received TEXT NOT NULL,slot TEXT NOT NULL,mode TEXT NOT NULL,band TEXT NOT NULL,dial INTEGER NOT NULL,snr INTEGER NOT NULL,dt REAL NOT NULL,offset INTEGER NOT NULL,message TEXT NOT NULL,raw TEXT NOT NULL)');return db

def parse_line(line):
 m=LINE.match(line)
 if not m:return None
 return dict(utc=m[1],snr=int(m[2]),dt=float(m[3]),offset=int(m[4]),message=m[5],raw=line)

def store(db,line,profile,frequency):
 parsed=parse_line(line)
 if parsed is None:return False
 now=datetime.datetime.now(datetime.timezone.utc)
 try:
  utc=datetime.datetime.strptime(parsed['utc'],'%H%M%S');slot=now.replace(hour=utc.hour,minute=utc.minute,second=utc.second,microsecond=0)
  if (slot-now).total_seconds()>43200:slot-=datetime.timedelta(days=1)
  elif (now-slot).total_seconds()>43200:slot+=datetime.timedelta(days=1)
 except ValueError:slot=now
 db.execute('INSERT INTO messages(received,slot,mode,band,dial,snr,dt,offset,message,raw) VALUES(?,?,?,?,?,?,?,?,?,?)',(now.isoformat(),slot.isoformat(),'msk144',MSK_PROFILES[profile][3],frequency,parsed['snr'],parsed['dt'],parsed['offset'],parsed['message'],line));db.commit();return True

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM messages WHERE received<?',(cutoff,));db.execute('DELETE FROM messages WHERE id<=(SELECT id FROM messages ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);db=connect();prune(db)
 import sys
 profile=sys.argv[1];frequency=MSK_PROFILES[profile][0]
 try:frequency=validate_msk_frequency(profile,json.loads((DATA/'msk-tuning.json').read_text()).get(profile,frequency))
 except FileNotFoundError:pass
 radio=subprocess.Popen(['/usr/bin/rtl_fm','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(frequency),'-M','usb','-s','12000','-g',str(SDR_GAIN),'-l','0','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 decoder=subprocess.Popen(['/usr/bin/stdbuf','-oL','-eL','/usr/local/bin/msk144decoder','--depth=3','--rxfreq=1500','--spot-reporter-enable=false','--file-log-enable=false'],stdin=radio.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 radio.stdout.close();stopping=False
 def stop(*_):
  global stopping
  stopping=True
  for p in (radio,decoder):
   if p.poll() is None:p.terminate()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 logs=collections.deque(maxlen=15);ntp=None;ntp_at=0;count=0;last=None;cleaned=time.monotonic();selector=selectors.DefaultSelector();buffers={}
 for stream in (radio.stderr,decoder.stdout,decoder.stderr):
  os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);buffers[stream.fileno()]=b''
 try:
  while selector.get_map() and not stopping:
   for key,_ in selector.select(timeout=1):
    fd=key.fileobj.fileno();chunk=os.read(fd,65536)
    if not chunk:selector.unregister(key.fileobj);continue
    buffers[fd]+=chunk
    while b'\n' in buffers[fd]:
     raw,buffers[fd]=buffers[fd].split(b'\n',1);line=raw.decode('utf-8',errors='replace').strip()
     if store(db,line,profile,frequency):count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
     elif line:logs.append(line[:1000]);print(line,flush=True)
   if time.monotonic()-cleaned>60:prune(db);cleaned=time.monotonic()
   if time.monotonic()-ntp_at>60:
    r=subprocess.run(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True,timeout=3);ntp=r.stdout.strip()=='yes';ntp_at=time.monotonic()
   state={'updated':time.time(),'profile':profile,'mode':'msk144','band':MSK_PROFILES[profile][3],'frequency':frequency,'session_count':count,'last_received':last,'logs':list(logs),'time_synced':ntp,'input_mode':'R820T tuner','depth':3}
   tmp=DATA/'msk-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'msk-state.json')
   if radio.poll() is not None or decoder.poll() is not None:
    if not stopping:raise RuntimeError('MSK144 receive pipeline exited unexpectedly')
 finally:
  stop()
  for p in (radio,decoder):
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  db.close()
