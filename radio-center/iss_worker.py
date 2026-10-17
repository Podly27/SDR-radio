#!/usr/bin/python3
"""Receive-only 145.800 MHz FM SSTV using OpenWebRX's native VIS decoder."""
import collections,datetime,io,json,os,selectors,signal,sqlite3,struct,subprocess,threading,time,uuid,wave
from pathlib import Path
from contextlib import closing
import numpy as np
from PIL import Image
from pycsdr.modules import Buffer,SstvDecoder
from pycsdr.types import Format
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
from iss_auto import load_config as iss_config
FREQUENCY=iss_config()['frequency']
MODES={0:'Robot 12',4:'Robot 24',32:'Martin 4',36:'Martin 3',48:'Scottie 4',51:'SC2 30',52:'Scottie 3',55:'SC2 180',59:'SC2 60',63:'SC2 120',8:'Robot 36',12:'Robot 72',40:'Martin 2',44:'Martin 1',56:'Scottie 2',60:'Scottie 1',76:'Scottie DX',93:'PD 50',94:'PD 290',95:'PD 120',96:'PD 180',97:'PD 240',98:'PD 160',99:'PD 90'}
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def connect(data=DATA):
 db=sqlite3.connect(Path(data)/'iss.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,received TEXT NOT NULL,started TEXT NOT NULL,filename TEXT UNIQUE NOT NULL,mode TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,lines INTEGER NOT NULL,complete INTEGER NOT NULL,frequency INTEGER NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS dashboard_images_received ON images(received)');db.commit();return db

def prune(data=DATA):
 data=Path(data)
 with closing(connect(data)) as db:
  cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=90)).isoformat()
  rows=db.execute('SELECT id,filename FROM images WHERE received<? OR id IN (SELECT id FROM images ORDER BY id DESC LIMIT -1 OFFSET 500)',(cutoff,)).fetchall()
  for ident,name in rows:
   (data/'iss-images'/Path(name).name).unlink(missing_ok=True);db.execute('DELETE FROM images WHERE id=?',(ident,))
  db.commit()

def save_png(path,header,pixels,width,height):
 full=header+pixels+b'\0'*(width*height*3-len(pixels))
 with Image.open(io.BytesIO(full)) as image:
  tmp=path.with_suffix('.tmp');image.convert('RGB').save(tmp,format='PNG');os.replace(tmp,path)

class Frames:
 def __init__(self,data=DATA,frequency=None):
  self.frequency=FREQUENCY if frequency is None else frequency;self.data=Path(data);self.directory=self.data/'iss-images';self.directory.mkdir(parents=True,exist_ok=True)
  self.buffer=bytearray();self.header=None;self.pixels=bytearray();self.width=0;self.height=0;self.lines=0;self.mode=None;self.started=None;self.count=0;self.last=None;self.preview_at=0;self.logs=collections.deque(maxlen=15);self.error=None
 def preview(self):
  if self.header and self.lines:
   save_png(self.directory/'preview.png',self.header,bytes(self.pixels),self.width,self.height);self.preview_at=time.monotonic()
 def finish(self,complete=False):
  if self.header and self.lines:
   self.preview();name=uuid.uuid4().hex+'.png'
   save_png(self.directory/name,self.header,bytes(self.pixels),self.width,self.height)
   received=stamp()
   with closing(connect(self.data)) as db:db.execute('INSERT INTO images(received,started,filename,mode,width,height,lines,complete,frequency) VALUES(?,?,?,?,?,?,?,?,?)',(received,self.started,name,self.mode,self.width,self.height,self.lines,int(complete),self.frequency));db.commit()
   self.count+=1;self.last=received;prune(self.data)
  self.header=None;self.pixels=bytearray();self.lines=0
 def feed(self,chunk):
  self.buffer.extend(chunk)
  while True:
   if self.header:
    if self.buffer.startswith(b' [FINISH-FRAME]'):
     del self.buffer[:15];self.finish(False);continue
    size=self.width*3
    if len(self.buffer)<size:return
    self.pixels.extend(self.buffer[:size]);del self.buffer[:size];self.lines+=1
    if self.lines==self.height:self.finish(True)
    elif time.monotonic()-self.preview_at>=2:self.preview()
   else:
    bmp=self.buffer.find(b'BM');msg=self.buffer.find(b' [')
    if msg>=0 and (bmp<0 or msg<bmp):
     end=self.buffer.find(b']',msg)
     if end<0:
      if len(self.buffer)>4096:del self.buffer[:-1]
      return
     self.logs.append(self.buffer[msg+2:end].decode(errors='replace')[:500]);del self.buffer[:end+1];continue
    if bmp<0:
     del self.buffer[:-1];return
    if bmp:del self.buffer[:bmp]
    if len(self.buffer)<54:return
    header=bytes(self.buffer[:54]);width,height=struct.unpack_from('<ii',header,18);bits=struct.unpack_from('<H',header,28)[0]
    if not (0<width<=1600 and -1200<=height<0 and width%4==0 and bits==24 and struct.unpack_from('<I',header,10)[0]==54):
     del self.buffer[:2];continue
    self.width=width;self.height=-height;self.header=header;self.pixels=bytearray();self.lines=0;self.mode=MODES.get(header[6],'VIS '+str(header[6]));self.started=stamp();self.preview_at=0;del self.buffer[:54]
 def state(self):
  return {'current_mode':self.mode if self.header else None,'lines':self.lines,'height':self.height if self.header else 0,'preview':bool(self.header and self.lines),'session_count':self.count,'last_received':self.last,'logs':list(self.logs)}

class Decoder:
 def __init__(self,frames):
  self.frames=frames;self.input=Buffer(Format.FLOAT,288000);self.output=Buffer(Format.CHAR,2097152);self.reader=self.output.getReader();self.decoder=SstvDecoder(24000,300000);self.error=None
  self.input_reader=self.input.getReader();self.decoder.setWriter(self.output);self.decoder.setReader(self.input_reader);self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()
 def read(self):
  try:
   while True:
    chunk=self.reader.read()
    if chunk is None:break
    self.frames.feed(chunk.tobytes())
  except Exception as exc:self.error=repr(exc)
 def feed(self,pcm):
  if self.error:raise RuntimeError(self.error)
  converted=(np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768).tobytes()
  for pos in range(0,len(converted),9600):
   deadline=time.monotonic()+3
   while True:
    try:self.input.write(converted[pos:pos+9600]);break
    except BufferError:
     if self.error or time.monotonic()>deadline:raise RuntimeError('SSTV decoder input stalled')
     time.sleep(.01)
 def close(self):
  self.decoder.stop();time.sleep(.2);self.reader.stop();self.thread.join(timeout=3)
  if self.thread.is_alive():raise RuntimeError('SSTV output thread did not stop')
  self.frames.finish(False)
  if self.error:raise RuntimeError(self.error)

def atomic(data,state):
 p=data/'iss-state.tmp';p.write_text(json.dumps(state,ensure_ascii=False));os.replace(p,data/'iss-state.json')

def replay(path,data):
 data=Path(data);data.mkdir(parents=True,exist_ok=True);frames=Frames(data);decoder=Decoder(frames)
 try:
  with wave.open(str(path)) as audio:
   if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())!=(1,2,24000):raise ValueError('Replay requires mono 16-bit PCM WAV at 24000 Hz')
   while chunk:=audio.readframes(2400):
    decoder.feed(chunk);time.sleep(len(chunk)/48000)  # The native ring buffer overwrites unread audio: replay at RF capture speed.
   decoder.feed(b'\0'*24000*4);time.sleep(1)
 finally:decoder.close()
 return frames.state()

def main():
 DATA.mkdir(parents=True,exist_ok=True);prune();frames=Frames();decoder=Decoder(frames);stopping=False;radio=None;logs=collections.deque(maxlen=15);audio_rms=None;last_state=0;pending=b''
 def stop(*_):
  nonlocal stopping
  stopping=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  radio=subprocess.Popen(['/usr/bin/rtl_fm','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(FREQUENCY),'-M','fm','-s','48000','-r','24000','-g',str(SDR_GAIN),'-l','0','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
  selector=selectors.DefaultSelector()
  for stream in (radio.stdout,radio.stderr):os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ)
  while not stopping:
   for key,_ in selector.select(timeout=.3):
    chunk=os.read(key.fileobj.fileno(),16384)
    if not chunk:
     if stopping:break
     raise RuntimeError('RTL-SDR audio stream ended')
    if key.fileobj is radio.stdout:
     pending+=chunk;length=len(pending)//2*2;pcm=pending[:length];pending=pending[length:]
     if pcm:audio_rms=float(np.sqrt(np.mean(np.frombuffer(pcm,dtype='<i2').astype(np.float32)**2)));decoder.feed(pcm)
    else:
     for line in chunk.decode(errors='replace').splitlines():logs.append(line[:500])
   if decoder.error:raise RuntimeError(decoder.error)
   if time.monotonic()-last_state>=1:
    state={'updated':time.time(),'frequency':FREQUENCY,'modulation':'FM','audio_rms':audio_rms,**frames.state()};state['logs']=list(logs)+state['logs'];atomic(DATA,state);last_state=time.monotonic()
   if not stopping and radio.poll() is not None:raise RuntimeError('RTL-SDR receiver exited')
 except Exception as exc:
  logs.append(str(exc));raise
 finally:
  if radio and radio.poll() is None:
   radio.terminate()
   try:radio.wait(timeout=3)
   except subprocess.TimeoutExpired:radio.kill();radio.wait()
  try:decoder.close()
  finally:atomic(DATA,{'updated':time.time(),'frequency':FREQUENCY,'stopped':True,**frames.state(),'logs':list(logs)+list(frames.logs)})
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--replay');parser.add_argument('--data',default=str(DATA));args=parser.parse_args()
 if args.replay:print(json.dumps(replay(args.replay,args.data),ensure_ascii=False))
 else:main()
