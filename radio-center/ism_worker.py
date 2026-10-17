#!/usr/bin/python3
import collections, datetime, json, os, selectors, signal, sqlite3, subprocess, time
from pathlib import Path
from sdr_calibration import SDR_PPM,SDR_GAIN,SDR_DEVICE,RTL433_DEVICE
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
FREQUENCIES=(433920000,868000000)
def receiver_frequency():
    try:frequency=json.loads((DATA/'ism-tuning.json').read_text())['frequency']
    except FileNotFoundError:return FREQUENCIES[0]
    if isinstance(frequency,bool) or frequency not in FREQUENCIES:raise ValueError('Neplatná ISM frekvence')
    return frequency

def connect():
    db=sqlite3.connect(DATA/'ism.sqlite',timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, received TEXT NOT NULL, model TEXT NOT NULL, device TEXT NOT NULL, payload TEXT NOT NULL)')
    return db

def store(db, payload):
    if not isinstance(payload,dict) or not payload.get('model'):return False
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    model=str(payload['model']);device=str(payload.get('id',payload.get('device',payload.get('channel',''))))
    db.execute('INSERT INTO events(received,model,device,payload) VALUES(?,?,?,?)',(now,model,device,json.dumps(payload,ensure_ascii=False)))
    db.commit();return True

def prune(db):
    cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat()
    db.execute('DELETE FROM events WHERE received < ?',(cutoff,))
    db.execute('DELETE FROM events WHERE id <= (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET 99999)')
    db.commit()

if __name__=='__main__':
    DATA.mkdir(parents=True,exist_ok=True);frequency=receiver_frequency();db=connect();prune(db)
    logs=collections.deque(maxlen=12);count=0;last=None;cleaned=time.monotonic()
    cmd=['/usr/bin/rtl_433','-c','0','-d',RTL433_DEVICE,'-p',str(SDR_PPM),'-f',str(frequency),'-s','1024k','-g',str(SDR_GAIN),'-Y','autolevel','-F','json','-F','log','-M','stats:2:30','-M','time:iso:utc','-M','protocol','-M','level','-C','si']
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    def stop(*_):
        if p.poll() is None:p.send_signal(signal.SIGINT)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    selector=selectors.DefaultSelector()
    buffers={}
    stats=None
    for stream,kind in [(p.stdout,'data'),(p.stderr,'log')]:
        os.set_blocking(stream.fileno(),False)
        selector.register(stream,selectors.EVENT_READ,kind)
        buffers[stream.fileno()]=b''
    while selector.get_map():
        for key,_ in selector.select(timeout=1):
            fd=key.fileobj.fileno()
            chunk=os.read(fd,65536)
            if not chunk:
                selector.unregister(key.fileobj);continue
            buffers[fd]+=chunk
            while b'\n' in buffers[fd]:
                raw,buffers[fd]=buffers[fd].split(b'\n',1)
                line=raw.decode('utf-8',errors='replace').strip()
                if not line:continue
                if key.data=='log':
                    logs.append(line);print(line,flush=True)
                else:
                    try:
                        payload=json.loads(line)
                        if isinstance(payload,dict) and payload.get('model'):payload['receiver_frequency']=frequency
                        if store(db,payload):
                            count+=1;last=datetime.datetime.now(datetime.timezone.utc).isoformat()
                        elif isinstance(payload,dict):stats=payload
                    except json.JSONDecodeError:
                        logs.append(line[:1000])
        if time.monotonic()-cleaned>60:
            prune(db);cleaned=time.monotonic()
        state={'updated':time.time(),'frequency':frequency,'session_count':count,'last_received':last,'logs':list(logs),'stats':stats,'sample_rate':1024000,'gain_db':SDR_GAIN,'autolevel':True}
        tmp=DATA/'ism-state.tmp';tmp.write_text(json.dumps(state));os.replace(tmp,DATA/'ism-state.json')
    rc=p.wait();db.close();raise SystemExit(0 if rc in (-signal.SIGINT,-signal.SIGTERM) else rc)
