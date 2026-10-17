#!/usr/bin/python3
import collections,datetime,json,os,re,selectors,signal,sqlite3,subprocess,time
from pathlib import Path
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
import base64,binascii
from aprs_worker import DATA,connect,prune,store

def store_frame(db,frame):
 if not isinstance(frame,dict) or frame.get('crc')!=1:return False
 try:data=base64.b64decode(frame.get('payload',''),validate=True)
 except (ValueError,TypeError,binascii.Error):return False
 if not data.startswith(b'\x3c\xff\x01'):return False
 raw=data[3:].split(b'\x00',1)[0].decode('utf-8',errors='replace').strip()
 if not re.match(r'^[A-Za-z0-9-]+>[^:]+:.+',raw):return False
 radio={k:v for k,v in frame.items() if k!='payload'}
 radio['frequency']=433775000
 return store(db,raw,radio)

if __name__=='__main__':
 DATA.mkdir(parents=True,exist_ok=True);db=connect('lora');prune(db)
 radio=subprocess.Popen(['/usr/bin/rtl_sdr','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f','433775000','-s','1000000','-g',str(SDR_GAIN),'-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 decoder=subprocess.Popen(['/usr/bin/stdbuf','-oL','-eL','/usr/bin/lorarx','-i','/dev/stdin','-f','u8','-r','1000000','-b','7','-s','9','-s','12','-W','50','-Q','-v','-N','-H','5','-M','433.775','-j','/dev/stdout'],stdin=radio.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 radio.stdout.close();stopping=False
 def stop(*_):
  global stopping
  stopping=True
  for p in (radio,decoder):
   if p.poll() is None:p.terminate()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 logs=collections.deque(maxlen=15);frames=0;rejected=0;count=0;last=None;cleaned=time.monotonic();selector=selectors.DefaultSelector();buffers={}
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
     if key.fileobj is decoder.stdout and line.startswith('{'):
      try:
       frame=json.loads(line);frames+=1
       if store_frame(db,frame):count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
       else:rejected+=1
      except (ValueError,TypeError):rejected+=1
     elif line:logs.append(line[:1000]);print(line,flush=True)
   if time.monotonic()-cleaned>60:prune(db);cleaned=time.monotonic()
   state={'updated':time.time(),'frequency':433775000,'session_count':count,'frames':frames,'rejected':rejected,'bandwidth':125000,'sf':[9,12],'last_received':last,'logs':list(logs)}
   tmp=DATA/'lora-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'lora-state.json')
   if radio.poll() is not None or decoder.poll() is not None:
    if not stopping:raise RuntimeError('LoRa APRS receive pipeline exited unexpectedly')
 finally:
  stop()
  for p in (radio,decoder):
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill();p.wait()
  db.close()
