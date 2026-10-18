#!/usr/bin/python3
"""Receive ISS SSTV, AFSK packet or voice; native DSP, no transmitting path."""
import collections,json,os,selectors,signal,struct,subprocess,time,shutil
from pathlib import Path
import numpy as np
import aprs_worker
import iss_auto as settings
from iss_worker import Frames,Decoder,atomic,stamp
from iss_dsp import Demodulator,RATE
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE
DATA=settings.common.DATA
RUN=Path(os.environ.get('RADIO_ISS_RUN','/run/radio-iss'))
class AudioWindow:
 def __init__(self):self.started=time.time();self.samples=0;self.tail=bytearray();self.last=0
 def feed(self,pcm):
  self.samples+=len(pcm)//2;self.tail.extend(pcm);del self.tail[:-96000]
  if time.monotonic()-self.last>=.2:
   p=RUN/'audio.tmp';p.write_bytes(struct.pack('<dQ',self.started,self.samples)+self.tail);os.replace(p,RUN/'audio.bin');self.last=time.monotonic()

def packet_command(config):
 return ['/usr/bin/stdbuf','-oL','-eL','/usr/bin/direwolf','-c',str(config),'-r','24000','-n','1','-b','16','-t','0','-']
def main():
 DATA.mkdir(parents=True,exist_ok=True);RUN.mkdir(parents=True,exist_ok=True);c=settings.load_config();p=settings.PROFILES[c['profile']];frames=Frames(frequency=c['frequency']);decoder=None;packet=None;db=None;radio=None;dsp=None;stopping=False;count=0;last=None;logs=collections.deque(maxlen=15);audio_rms=None;tuning=settings.tuning(c);buffers={};raw_pending=b'';last_state=0;last_tuning=0;last_cleanup=time.monotonic();window=AudioWindow();iq_record=None;record_until=0
 try:
  plan=json.loads((DATA/'iss-diagnostic-plan.json').read_text());record_until=float(plan['expires'])
  if time.time()<record_until<time.time()+1800 and p['kind']=='packet' and shutil.disk_usage(DATA).free>1024**3:
   folder=DATA/'iss-diagnostics'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());folder.mkdir(parents=True,exist_ok=True);iq_record=(folder/'iq.cu8').open('wb');(folder/'metadata.json').write_text(json.dumps({'started':time.time(),'config':c,'samplerate':RATE,'gain':SDR_GAIN,'ppm':SDR_PPM,'device':SDR_DEVICE}))
 except (OSError,ValueError,KeyError,TypeError):pass
 def stop(*_):
  nonlocal stopping
  stopping=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  if p['kind']=='sstv':decoder=Decoder(frames)
  elif p['kind']=='packet':
   db=aprs_worker.connect('iss-packet');aprs_worker.prune(db)
   config=DATA/'iss-direwolf.conf';config.write_text('ADEVICE stdin null\nARATE 24000\nACHANNELS 1\nCHANNEL 0\nMYCALL '+settings.common.station()['callsign']+'\nMODEM 1200\nFIX_BITS 0\nAGWPORT 0\nKISSPORT 0\n')
   packet=subprocess.Popen(packet_command(config),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
  def audio(pcm):
   nonlocal audio_rms
   if pcm:
    audio_rms=float(np.sqrt(np.mean(np.frombuffer(pcm,dtype='<i2').astype(np.float32)**2)));window.feed(pcm)
    if decoder:decoder.feed(pcm)
    if packet:
     # Dire Wolf reported level 150 on real ISS audio; /3 gives level 50
     # while preserving the same valid AX.25 frame in replay.
     packet_pcm=(np.frombuffer(pcm,dtype='<i2').astype(np.float32)/3).astype('<i2').tobytes()
     remaining=memoryview(packet_pcm)
     while remaining:
      size=packet.stdin.write(remaining)
      if not size:raise RuntimeError('Packet audio input ended')
      remaining=remaining[size:]
  dsp=Demodulator(audio,voice=p['kind']=='voice');dsp.tune(tuning['doppler_hz'])
  radio=subprocess.Popen(['/usr/bin/rtl_sdr','-d',SDR_DEVICE,'-p',str(SDR_PPM),'-f',str(c['frequency']),'-s',str(RATE),'-g',str(SDR_GAIN),'-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
  selector=selectors.DefaultSelector()
  streams=[radio.stdout,radio.stderr]+([packet.stdout,packet.stderr] if packet else [])
  for stream in streams:os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ);buffers[stream.fileno()]=b''
  while not stopping:
   for key,_ in selector.select(timeout=.2):
    chunk=os.read(key.fileobj.fileno(),32768)
    if not chunk:
     if stopping:break
     raise RuntimeError('ISS receiver stream ended')
    if key.fileobj is radio.stdout:
     if iq_record:
      if time.time()<record_until and iq_record.tell()<RATE*2*600:iq_record.write(chunk)
      else:iq_record.close();iq_record=None
     raw_pending+=chunk;n=len(raw_pending)//2*2
     if n:dsp.feed(raw_pending[:n]);raw_pending=raw_pending[n:]
    else:
     fd=key.fileobj.fileno();buffers[fd]+=chunk
     while b'\n' in buffers[fd]:
      line,buffers[fd]=buffers[fd].split(b'\n',1);line=line.decode(errors='replace').strip();match=aprs_worker.PACKET.match(line) if packet and key.fileobj is packet.stdout else None
      if match:
       if aprs_worker.store(db,match[1],{'frequency':c['frequency'],'profile':c['profile'],'doppler_hz':tuning['doppler_hz']}):count+=1;last=stamp()
      elif line:logs.append(line[:500])
   if time.monotonic()-last_tuning>=1:
    tuning=settings.tuning(c);dsp.tune(tuning['doppler_hz']);last_tuning=time.monotonic()
   if db and time.monotonic()-last_cleanup>=60:aprs_worker.prune(db);last_cleanup=time.monotonic()
   if dsp.error or (decoder and decoder.error):raise RuntimeError(dsp.error or decoder.error)
   if radio.poll() is not None or (packet and packet.poll() is not None):raise RuntimeError('ISS receive pipeline exited')
   if time.monotonic()-last_state>=1:
    state={**frames.state(),'updated':time.time(),'profile':c['profile'],'kind':p['kind'],'frequency':c['frequency'],'modulation':'FM','audio_rms':audio_rms,**tuning}
    if p['kind']!='sstv':state.update(session_count=count,last_received=last)
    state['logs']=list(logs)+list(frames.logs);atomic(DATA,state);last_state=time.monotonic()
 except Exception as exc:logs.append(str(exc));raise
 finally:
  if iq_record:iq_record.close()
  if radio and radio.poll() is None:
   radio.terminate()
   try:radio.wait(timeout=3)
   except subprocess.TimeoutExpired:radio.kill();radio.wait()
  # Close the packet process before stopping the DSP in case its stdin is blocked.
  if packet and packet.poll() is None:
   packet.terminate()
   try:packet.wait(timeout=2)
   except subprocess.TimeoutExpired:packet.kill();packet.wait()
  try:
   if dsp:dsp.close()
  finally:
   if decoder:decoder.close()
   if db:db.close()
   atomic(DATA,{'updated':time.time(),'profile':c['profile'],'kind':p['kind'],'frequency':c['frequency'],'stopped':True,**frames.state(),'session_count':frames.count if decoder else count,'last_received':frames.last if decoder else last,'logs':list(logs)+list(frames.logs),**tuning})
if __name__=='__main__':main()
