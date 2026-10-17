#!/usr/bin/python3
"""Receive one 90 kHz EME window and feed the existing MAP65 file decoder."""
import collections,datetime,itertools,json,os,queue,selectors,signal,sqlite3,struct,subprocess,tempfile,threading,time,wave
from pathlib import Path
import numpy as np
from scipy.signal import firwin,upfirdn,resample_poly
from ft_worker import parse_line as parse_jt9
import eme_common as common
RATE=96000
class Resampler:
 def __init__(self):
  self.h=(2*firwin(801,46500,fs=480000)).astype(np.float32);self.history=np.zeros(400,np.complex64)
 def feed(self,x):
  if len(x)%5:raise ValueError('Input block must be a multiple of 5')
  combined=np.concatenate((self.history,x));y=upfirdn(self.h,combined,up=2,down=5)
  self.history=combined[-400:].copy();y=y[160:160+len(x)*2//5]
  # MAP65/Linrad stores conjugated IQ with its zero at the Nyquist bin.
  y=np.conj(y);y[1::2]*=-1
  out=np.empty((len(y),2),dtype='<i2');out[:,0]=np.clip(y.real*256,-32768,32767);out[:,1]=np.clip(y.imag*256,-32768,32767)
  return out.tobytes()
class IQSlots:
 def __init__(self):self.tick=None;self.current=None;self.buffer=bytearray();self.complete=False
 def feed(self,data,now):
  if self.tick is None:self.tick=round(now*RATE-len(data)/4)
  size=60*RATE;out=[];pos=0
  while pos<len(data):
   index=self.tick//size;offset=self.tick%size
   if self.current!=index:self.current=index;self.buffer.clear();self.complete=offset==0
   n=min(size-offset,(len(data)-pos)//4);self.buffer.extend(data[pos:pos+4*n]);self.tick+=n;pos+=4*n
   if n==size-offset:
    if self.complete:out.append((index*60,bytes(self.buffer)))
    self.current=None;self.buffer.clear()
  return out

def parse_log(line):
 try:
  if len(line)<64 or line[61] not in '#:' or line[63] not in 'ABCDE':return None
  mode='Q65' if line[61]==':' else 'JT65';sub=line[63]
  message=line[33:61 if mode=='Q65' else 55].strip()
  if not message:return None
  return dict(frequency=round(float(line[:8])*1e6+int(line[8:13])),snr=int(line[22:26]),dt=float(line[13:18]),mode=mode,submode=('60'+sub) if mode=='Q65' else sub,message=message,raw=line)
 except ValueError:return None

def save(db,slot,c,p):
 now=datetime.datetime.now(datetime.timezone.utc).isoformat();stamp=datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).isoformat()
 db.execute('INSERT OR IGNORE INTO messages(received,slot,frequency,band,mode,submode,snr,dt,message,raw) VALUES(?,?,?,?,?,?,?,?,?,?)',(now,stamp,p['frequency'],c['band'],p['mode'],p['submode'],p['snr'],p['dt'],p['message'],p['raw']));db.commit()

def jt65_audio(path,output,center,dial):
 raw=np.memmap(path,dtype='<i2',mode='r',offset=8).reshape(-1,2)
 with wave.open(str(output),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(12000)
  for i in range(0,len(raw),RATE):
   a=max(0,i-128);b=min(len(raw),i+RATE+128);n=np.arange(a,b)
   x=raw[a:b,0].astype(np.float32)+1j*raw[a:b,1].astype(np.float32);x[1::2]*=-1;x=np.conj(x)
   x*=np.exp(-2j*np.pi*(dial-center)*n/RATE)
   audio=resample_poly(x.real,1,8)[(i-a)//8:(i-a)//8+min(RATE,len(raw)-i)//8]
   w.writeframes(np.clip(audio,-32768,32767).astype('<i2').tobytes())

def main():
 c=common.validate(common.load_config());start=c['starts'][c['band']];center=start+45000
 common.DATA.mkdir(parents=True,exist_ok=True);db=common.connect();common.prune(db);db.close()
 stop=threading.Event();work=queue.Queue(maxsize=1);decoder_holder=[None];logs=collections.deque(maxlen=18)
 state={'band':c['band'],'start':start,'end':start+common.WIDTH,'frequency':center,'sample_rate':240000,'iq_rate':RATE,'session_count':0,'cycles':0,'skipped':0,'passes':[],'last_received':None,'errors':0,'capture':'starting','updated':time.time(),'config':c,'current_pass':None,'last_cycle':None,'decode_seconds':None,'rms':None,'queue':0,'last_sample':None,'logs':[],'jt65_candidates_found':0,'jt65_candidates_skipped':0,'planned_q65':[],'planned_jt65':[]}
 def log(s):logs.append(str(s)[-900:]);print(s,flush=True)
 def decode():
  db=common.connect()
  try:
   while not stop.is_set():
    try:slot,audio=work.get(timeout=.5)
    except queue.Empty:continue
    began=time.monotonic();results=[];cycle=state['cycles']
    qlist=sorted(c['q65'],key=lambda q:('BCADE' if c['band']=='70cm' else 'ABCDE').index(q))
    jlist=c['jt65']
    if c['strategy']=='rotate':
     # A Pi 3 cannot guarantee Q65 and JT65 together for every 60 s record.
     # Alternate protocol jobs and rotate submodes automatically; never hide gaps.
     if qlist and jlist:
      if cycle%2==0:qlist=[qlist[(cycle//2)%len(qlist)]];jlist=[]
      else:jlist=[jlist[(cycle//2)%len(jlist)]];qlist=[]
     else:
      qlist=[qlist[cycle%len(qlist)]] if qlist else [];jlist=[jlist[cycle%len(jlist)]] if jlist else []
    pairs=list(itertools.zip_longest(jlist,qlist,fillvalue='0'));state['planned_q65']=qlist;state['planned_jt65']=jlist
    try:
     with tempfile.TemporaryDirectory(prefix='eme-') as td:
      td=Path(td);stamp=datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).strftime('%y%m%d_%H%M');path=td/(stamp+'.iq');path.write_bytes(struct.pack('<d',center/1e6)+audio);del audio
      jsubs=''.join(j for j,q in pairs);qsubs=''.join(q for j,q in pairs)
      run=td/'decode';run.mkdir();(run/'wsjtx_dir.txt').write_text(str(run)+'\n')
      command=['/opt/radio-center/eme-m65',jsubs,qsubs,'N','96000',c['callsign'],common.location_grid(c['latitude'],c['longitude']),str((start-center//1000000*1000000)//1000),str((start-center//1000000*1000000)//1000+90),str(path)]
      state['current_pass']={'jt65':jsubs,'q65':qsubs};timed_out=False
      with subprocess.Popen(command,cwd=run,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')) as p:
       decoder_holder[0]=p
       try:
        if stop.is_set():p.terminate()
        stdout,stderr=p.communicate(timeout=55)
       except subprocess.TimeoutExpired:
        p.kill();stdout,stderr=p.communicate();timed_out=True;state['errors']+=1;state['skipped']+=1;log('Výpočetní rozpočet 55 s vyčerpán; nedokončené průchody vynechány.')
       finally:decoder_holder[0]=None
      if p.returncode and not stop.is_set() and not timed_out:state['errors']+=1;log('MAP65: '+(stderr or stdout)[-900:])
      done={}
      for line in stdout.splitlines():
       fields=line.split()
       if len(fields)==3 and fields[0]=='EME_PASS_DONE':
        done[fields[1]]=float(fields[2])
      parsed_rows=[];logpath=run/'map65_rx.log'
      if logpath.exists():
       for line in logpath.read_text(errors='replace').splitlines():
        parsed=parse_log(line)
        if parsed:
         save(db,slot,c,parsed);parsed_rows.append(parsed);state['session_count']+=1;state['last_received']=datetime.datetime.now(datetime.timezone.utc).isoformat()
      # MAP65 supplies wideband synchronization candidates; use the packaged
      # WSJT-X JT65 decoder for their small USB slices, without scanning 30 channels.
      candidates=[]
      for line in stdout.splitlines():
       fields=line.split()
       if len(fields)==3 and fields[0]=='EME_JT_CANDIDATE':
        frequency=float(fields[1])
        if not any(abs(frequency-f)<100 for f in candidates):candidates.append(frequency)
      state['jt65_candidates_found']=len(candidates);state['jt65_candidates_skipped']=max(0,len(candidates)-c['jt65_candidates']) if jlist else 0
      for index,frequency in enumerate(candidates[:c['jt65_candidates']] if jlist else []):
       if stop.is_set():break
       wav=td/(stamp+'.wav');dial=frequency-1500;jt65_audio(path,wav,center,dial)
       for sub in jlist:
        if stop.is_set():break
        remaining=55-(time.monotonic()-began)
        if remaining<2:state['skipped']+=1;log('JT65: výpočetní rozpočet vyčerpán; kandidát vynechán.');break
        command=['/usr/bin/jt9','--jt65','-b',sub,'-p','60','-d','2','-L','1000','-H','2000','-f','1500','-F','100','-c',c['callsign'],'-x','b',str(wav)]
        with subprocess.Popen(command,cwd=td,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,OMP_NUM_THREADS='1')) as decoder:
         decoder_holder[0]=decoder;started=time.monotonic()
         try:
          if stop.is_set():decoder.terminate()
          out,err=decoder.communicate(timeout=remaining)
         except subprocess.TimeoutExpired:
          decoder.kill();out,err=decoder.communicate();state['errors']+=1;state['skipped']+=1;log('JT65: překročen časový limit.')
         finally:decoder_holder[0]=None
        count=0
        for line in out.splitlines():
         parsed=parse_jt9(line,'jt65'+sub.lower())
         if parsed:
          parsed.update(frequency=round(dial+parsed['offset']-1270.46),mode='JT65',submode=sub)
          save(db,slot,c,parsed);count+=1;state['session_count']+=1;state['last_received']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        results.append({'jt65':sub,'q65':'0','candidate':frequency,'state':'ok' if decoder.returncode==0 else 'error','seconds':round(time.monotonic()-started,2),'count':count})
      for jsub,qsub in pairs:
       if qsub=='0':continue
       code=jsub+qsub;results.append({'jt65':'0','q65':qsub,'state':'ok' if code in done else 'timeout' if timed_out else 'error','seconds':round(done[code],2) if code in done else None,'count':sum((x['mode']=='JT65' and x['submode']==jsub) or (x['mode']=='Q65' and x['submode']=='60'+qsub) for x in parsed_rows)})
      state['passes']=results;state['current_pass']=None;state['cycles']+=1;state['last_cycle']=datetime.datetime.fromtimestamp(slot,datetime.timezone.utc).isoformat();state['decode_seconds']=round(time.monotonic()-began,2);common.prune(db)
    except (OSError,ValueError,sqlite3.Error) as e:state['errors']+=1;log('Dekodér: '+str(e))
    finally:work.task_done()
  finally:db.close()
 thread=threading.Thread(target=decode,daemon=True);thread.start()
 command=['/usr/bin/rtl_sdr','-d',c['device'],'-f',str(center),'-s','240000','-g',str(c['gain']),'-p',str(c['ppm']),'-']
 radio=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
 def finish(*_):
  stop.set()
  for proc in (radio,decoder_holder[0]):
   if proc is not None and proc.poll() is None:
    try:proc.terminate()
    except ProcessLookupError:pass
 signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
 selector=selectors.DefaultSelector()
 for stream,kind in ((radio.stdout,'iq'),(radio.stderr,'log')):os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,kind)
 pending=b'';errors=b'';slots=IQSlots();resampler=Resampler();last_write=0;last_sample=None;capture_started=time.time()
 try:
  while not stop.is_set():
   for key,_ in selector.select(timeout=.5):
    data=os.read(key.fileobj.fileno(),96000)
    if not data:selector.unregister(key.fileobj);continue
    if key.data=='log':
     errors+=data
     while b'\n' in errors:line,errors=errors.split(b'\n',1);log(line.decode(errors='replace'))
    else:
     pending+=data
     while len(pending)>=48000:
      block,pending=pending[:48000],pending[48000:];u=np.frombuffer(block,dtype=np.uint8).astype(np.float32)-127.5;x=(u[::2]+1j*u[1::2]).astype(np.complex64)
      filtered=resampler.feed(x);now=time.time();last_sample=now;state['capture']='receiving';state['rms']=round(float(np.sqrt(np.mean(np.abs(x)**2))),2)
      for slot,iq in slots.feed(filtered,now):
       try:work.put_nowait((slot,iq))
       except queue.Full:state['skipped']+=1;log('Fronta dekódování plná; interval vynechán.')
   now=time.time()
   if now-last_write>=1:
    state.update(updated=now,logs=list(logs),queue=work.qsize(),last_sample=last_sample);common.atomic('eme-state.json',state);last_write=now
   if stop.is_set():break
   if radio.poll() is not None:raise RuntimeError('RTL-SDR ukončil příjem')
   if now-(last_sample if last_sample is not None else capture_started)>10:raise RuntimeError('RTL-SDR neposílá IQ data déle než 10 s')
 finally:
  finish();radio.wait(timeout=5);thread.join(timeout=5);state['capture']='stopped';state['updated']=time.time();common.atomic('eme-state.json',state)
if __name__=='__main__':main()
