#!/usr/bin/python3
"""UTC-aligned 12 kHz USB capture and bounded WSJT-X decode queue."""
import collections,datetime,json,os,queue,re,selectors,signal,sqlite3,subprocess,sys,tempfile,threading,time,wave
from pathlib import Path
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
KIND=os.environ.get('RADIO_DECODER_KIND','ft')
if KIND not in ('ft','weak'):raise ValueError('Unsupported decoder kind')
if KIND=='weak':from weak_profiles import PROFILES,validate_frequency
else:from ft_profiles import PROFILES,validate_frequency
LINE=re.compile(r'^\s*(\d{4}|\d{6})\s+(-?\d+)\s+([+-]?[\d.]+)\s+(\d+)\s+([~+#:])\s+(.+?)\s*$')
def connect():
 db=sqlite3.connect(DATA/(KIND+'.sqlite'),timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,received TEXT NOT NULL,slot TEXT NOT NULL,mode TEXT NOT NULL,band TEXT NOT NULL,dial INTEGER NOT NULL,snr INTEGER NOT NULL,dt REAL NOT NULL,offset INTEGER NOT NULL,message TEXT NOT NULL,raw TEXT NOT NULL)');return db

def parse_line(line,mode=None):
 m=LINE.match(line)
 if not m:return None
 expected=':' if mode and mode.startswith('q65') else '#' if mode and mode.startswith('jt65') else None
 if expected and m[5]!=expected:return None
 message=m[6]
 if m[5]==':':message=re.sub(r'\s+q[0-9*]+\s*$','',message).strip()
 return dict(snr=int(m[2]),dt=float(m[3]),offset=int(m[4]),message=message,raw=line)

def decoder_command(mode,period,path):
 if mode.startswith('q65-'):
  decoder='q65';sub=mode[-1].upper()
 elif mode.startswith('jt65'):
  decoder='jt65';sub=mode[-1].upper()
 else:return ['/usr/bin/jt9','--'+mode,'-d','2',str(path)]
 return ['/usr/bin/jt9','--'+decoder,'-p',str(period),'-b',sub,'-d','2','-L','200','-H','4000','-f','1500','-F','1000','-c','b','-x','b',str(path)]

def save(db,slot,profile,parsed):
 freq,_,mode,band=PROFILES[profile]
 db.execute('INSERT INTO messages(received,slot,mode,band,dial,snr,dt,offset,message,raw) VALUES(?,?,?,?,?,?,?,?,?,?)',(datetime.datetime.now(datetime.timezone.utc).isoformat(),datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).isoformat(),mode,band,freq,parsed['snr'],parsed['dt'],parsed['offset'],parsed['message'],parsed['raw']));db.commit()

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM messages WHERE received<?',(cutoff,));db.execute('DELETE FROM messages WHERE id<=(SELECT id FROM messages ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

class Slots:
 def __init__(self,period,rate=12000):self.period=period;self.rate=rate;self.tick=None;self.current=None;self.buffer=bytearray();self.complete=False;self.carry=b''
 def feed(self,chunk,now):
  chunk=self.carry+chunk;self.carry=chunk[len(chunk)//2*2:];chunk=chunk[:len(chunk)//2*2]
  if not chunk:return []
  if self.tick is None:self.tick=round(now*self.rate-len(chunk)/2)
  size=round(self.period*self.rate);out=[];pos=0
  while pos<len(chunk):
   index=self.tick//size;offset=self.tick%size
   if self.current!=index:self.current=index;self.buffer.clear();self.complete=offset==0
   remaining=size-offset;n=min(remaining,(len(chunk)-pos)//2)
   self.buffer.extend(chunk[pos:pos+2*n]);self.tick+=n;pos+=2*n
   if n==remaining:
    if self.complete:out.append((index*self.period,bytes(self.buffer)))
    self.current=None;self.buffer.clear()
  return out

if __name__=='__main__':
 profile=sys.argv[1];freq,period,mode,band=PROFILES[profile]
 try:
  tuning=json.loads((DATA/(KIND+'-tuning.json')).read_text());freq=validate_frequency(profile,tuning.get(profile,freq))
 except FileNotFoundError:pass
 PROFILES[profile]=(freq,period,mode,band)
 DATA.mkdir(parents=True,exist_ok=True);db=connect();prune(db);db.close()
 decode_timeout=55 if KIND=='weak' else 25
 decoder_process=[None]
 state={'profile':profile,'mode':mode,'band':band,'frequency':freq,'period':period,'session_count':0,'cycles':0,'skipped':0,'last_received':None,'last_cycle':None,'decode_seconds':None,'audio_rms':None,'logs':[]}
 logs=collections.deque(maxlen=12);work=queue.Queue(maxsize=1 if KIND=='weak' else 2);stopped=threading.Event()
 def log(msg):logs.append(str(msg)[:1000]);print(msg,flush=True)
 def decode():
  db=connect()
  try:
   while not stopped.is_set():
    try:item=work.get(timeout=.5)
    except queue.Empty:continue
    slot,audio=item;started=time.monotonic()
    try:
     with tempfile.TemporaryDirectory(prefix='ft-') as td:
      stamp=datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).strftime('%y%m%d_%H%M%S');p=Path(td)/(stamp+'.wav')
      with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(12000);w.writeframes(audio)
      with subprocess.Popen(decoder_command(mode,period,p),cwd=td,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,OMP_NUM_THREADS='1')) as decoder:
       decoder_process[0]=decoder
       try:
        if stopped.is_set():decoder.terminate()
        stdout,stderr=decoder.communicate(timeout=decode_timeout)
       except subprocess.TimeoutExpired:
        decoder.kill();decoder.communicate();raise
       finally:decoder_process[0]=None
      if decoder.returncode:log('jt9: '+(stderr or stdout)[-600:])
      else:
       for line in stdout.splitlines():
        parsed=parse_line(line,mode)
        if parsed:save(db,slot,profile,parsed);state['session_count']+=1;state['last_received']=datetime.datetime.now(datetime.timezone.utc).isoformat()
      state['cycles']+=1;state['last_cycle']=datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).isoformat();state['decode_seconds']=round(time.monotonic()-started,2);prune(db)
    except subprocess.TimeoutExpired:log(f'Dekódování překročilo {decode_timeout} s; interval vynechán.');state['skipped']+=1
    except (OSError,sqlite3.Error) as e:log('Chyba dekódování: '+str(e));state['skipped']+=1
    finally:work.task_done()
  finally:db.close()
 thread=threading.Thread(target=decode,daemon=True);thread.start()
 command=['/usr/bin/rtl_fm','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(freq),'-M','usb','-s','12000','-l','0']
 if freq<24000000:command+=['-E','direct2']
 else:command+=['-g',str(SDR_GAIN)]
 command+=['-']
 state['input_mode']='direct Q' if freq<24000000 else 'R820T tuner'
 radio=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 def stop(*_):
  stopped.set()
  if radio.poll() is None:radio.terminate()
  decoder=decoder_process[0]
  if decoder is not None and decoder.poll() is None:
   try:decoder.terminate()
   except ProcessLookupError:pass
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 selector=selectors.DefaultSelector();errors=b'';slots=Slots(period);last_ntp=0
 for stream,kind in [(radio.stdout,'audio'),(radio.stderr,'log')]:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,kind)
 try:
  while not stopped.is_set():
   for key,_ in selector.select(timeout=.3):
    chunk=os.read(key.fileobj.fileno(),65536)
    if not chunk:selector.unregister(key.fileobj);continue
    if key.data=='log':
     errors+=chunk
     while b'\n' in errors:line,errors=errors.split(b'\n',1);log(line.decode(errors='replace'))
    else:
     # RMS is relative audio level, not calibrated RF power.
     import array,math
     samples=array.array('h',chunk[:len(chunk)//2*2]);state['audio_rms']=round(math.sqrt(sum(x*x for x in samples)/len(samples)),1) if samples else 0
     for slot,audio in slots.feed(chunk,time.time()):
      try:work.put_nowait((slot,audio))
      except queue.Full:state['skipped']+=1;log('Fronta plná; interval vynechán.')
   if time.monotonic()-last_ntp>60:
    r=subprocess.run(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True,timeout=3);state['time_synced']=r.stdout.strip()=='yes';last_ntp=time.monotonic()
   state['updated']=time.time();state['logs']=list(logs);state['queue']=work.qsize();tmp=DATA/(KIND+'-state.tmp');tmp.write_text(json.dumps(state));os.replace(tmp,DATA/(KIND+'-state.json'))
   if radio.poll() is not None and not stopped.is_set():raise RuntimeError('RTL-SDR audio capture ended')
 finally:
  stop()
  try:radio.wait(timeout=3)
  except subprocess.TimeoutExpired:radio.kill();radio.wait()
  thread.join(timeout=decode_timeout+2)
