#!/usr/bin/python3
"""Local dump1090-fa integration. No network feeds or RF transmissions."""
import datetime,json,math,os,signal,sqlite3,subprocess,time
from pathlib import Path
from contextlib import closing
import station_common as station
DATA=station.DATA
RUN=Path(os.environ.get('RADIO_ADSB_RUN','/run/radio-adsb'))
DEFAULT={'gain_mode':'adaptive','gain':None}
def validate_config(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné nastavení ADS-B')
 c={**DEFAULT,**raw}
 if c['gain_mode'] not in ('adaptive','manual'):raise ValueError('Neplatný režim zisku')
 if c['gain'] is not None:
  if isinstance(c['gain'],bool):raise ValueError('Neplatný zisk')
  try:c['gain']=float(c['gain'])
  except (TypeError,ValueError):raise ValueError('Neplatný zisk')
  if not math.isfinite(c['gain']) or not 0<=c['gain']<=49.6:raise ValueError('Zisk musí být 0–49,6 dB')
 return {k:c[k] for k in DEFAULT}
def load_config():
 try:return validate_config(json.loads((DATA/'adsb-config.json').read_text()))
 except FileNotFoundError:return dict(DEFAULT)
def rf_stats():
 try:
  raw=json.loads((RUN/'stats.json').read_text());period=raw.get('last1min') or raw.get('total',{});local=period.get('local',{});seconds=max(1,period.get('end',0)-period.get('start',0));accepted=sum(local.get('accepted',[]));cpr=period.get('cpr',{});samples=local.get('samples_processed',0);dropped=local.get('samples_dropped',0)
  return {'updated':raw.get('total',{}).get('end'),'period_seconds':seconds,'messages_per_second':accepted/seconds,'accepted':accepted,'gain_db':local.get('gain_db',raw.get('total',{}).get('local',{}).get('gain_db')),'signal_dbfs':local.get('signal'),'noise_dbfs':local.get('noise'),'samples_dropped':dropped,'drop_percent':100*dropped/max(1,samples+dropped),'strong_signals':local.get('strong_signals',0),'positions':cpr.get('global_ok',0)+cpr.get('local_ok',0),'cpr_rejected':cpr.get('global_bad',0),'raw':raw}
 except (OSError,ValueError,TypeError):return None

def valid_position(a):
 return all(isinstance(a.get(k),(int,float)) and not isinstance(a[k],bool) and math.isfinite(a[k]) and abs(a[k])<=limit for k,limit in [('lat',90),('lon',180)])
def live_aircraft(raw,cached,now=None):
 now=raw['now'] if now is None else now;result=[]
 for original in raw.get('aircraft',[]):
  if original.get('seen',999)>=300:continue
  a=dict(original);a['position_source']=None;a['position_age']=None
  if valid_position(a) and isinstance(a.get('seen_pos'),(int,float)):
   a['position_age']=max(0,now-raw['now']+a['seen_pos']);a['position_source']='local'
  elif a.get('hex') in cached:
   pos=cached[a['hex']];age=now-pos['received']
   if 0<=age<=300:a.update(lat=pos['lat'],lon=pos['lon'],position_age=age,position_source='last_local')
  result.append(a)
 return sorted(result,key=lambda a:a.get('seen',999))

def connect():
 db=sqlite3.connect(DATA/'adsb.sqlite',timeout=5);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,received TEXT NOT NULL,hex TEXT NOT NULL,flight TEXT NOT NULL,payload TEXT NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS adsb_events_received ON events(received)');db.execute('CREATE INDEX IF NOT EXISTS adsb_events_hex ON events(hex,id)')
 db.execute('CREATE TABLE IF NOT EXISTS positions(hex TEXT PRIMARY KEY,received REAL NOT NULL,lat REAL NOT NULL,lon REAL NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS adsb_positions_received ON positions(received)')
 db.execute('CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,received TEXT NOT NULL,messages_delta INTEGER NOT NULL)');db.execute('CREATE INDEX IF NOT EXISTS adsb_samples_received ON samples(received)');db.commit();return db

def command(c,config=None):
 config=load_config() if config is None else validate_config(config)
 cmd=['/usr/bin/dump1090-fa','--device-type','rtlsdr','--device',c['device'],'--gain',str(c['gain'] if config['gain'] is None else config['gain']),'--ppm',str(c['ppm']),'--freq','1090000000','--quiet','--write-json',str(RUN),'--write-json-every','1','--json-location-accuracy','2','--json-stats-every','5','--fix']
 if config['gain_mode']=='adaptive':cmd+=['--adaptive-range','--adaptive-min-gain','20.7','--adaptive-max-gain','49.6','--adaptive-duty-cycle','20']
 if c['latitude'] is not None:cmd+=['--lat',str(c['latitude']),'--lon',str(c['longitude'])]
 return cmd

def ingest(db,raw,previous):
 stamp=datetime.datetime.fromtimestamp(raw['now'],datetime.timezone.utc).isoformat();total=int(raw.get('messages',0));old_total,old_planes=previous;delta=max(0,total-old_total) if total>=old_total else total;seen={}
 if delta:db.execute('INSERT INTO samples(received,messages_delta) VALUES(?,?)',(stamp,delta))
 for a in raw.get('aircraft',[]):
  key=a.get('hex','');count=int(a.get('messages',0));seen[key]=count
  age=a.get('seen_pos')
  if key and valid_position(a) and isinstance(age,(int,float)) and math.isfinite(age) and 0<=age<=300:
   db.execute('INSERT INTO positions(hex,received,lat,lon) VALUES(?,?,?,?) ON CONFLICT(hex) DO UPDATE SET received=excluded.received,lat=excluded.lat,lon=excluded.lon WHERE excluded.received>positions.received',(key,raw['now']-age,a['lat'],a['lon']))
  if not key or count==old_planes.get(key,0) or a.get('seen',999)>15:continue
  db.execute('INSERT INTO events(received,hex,flight,payload) VALUES(?,?,?,?)',(stamp,key,str(a.get('flight','')).strip(),json.dumps(a,allow_nan=False)))
 db.commit();return total,seen,delta

def summary():
 result={'hour_count':0,'minute_count':0,'last_received':None,'available':True,'receiver':None}
 p=DATA/'adsb.sqlite'
 if p.exists():
  try:
   with closing(sqlite3.connect(f'file:{p}?mode=ro',uri=True,timeout=.3)) as db:
    cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1)).isoformat();result['hour_count']=db.execute('SELECT coalesce(sum(messages_delta),0) FROM samples WHERE received>=?',(cutoff,)).fetchone()[0];result['last_received']=db.execute('SELECT max(received) FROM samples').fetchone()[0]
    minute_cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)).isoformat();result['minute_count']=db.execute('SELECT coalesce(sum(messages_delta),0) FROM samples WHERE received>=?',(minute_cutoff,)).fetchone()[0]
  except sqlite3.Error:result.update(available=False,error='Historie ADS-B není dostupná')
 try:result['receiver']=json.loads((DATA/'adsb-state.json').read_text())
 except (OSError,ValueError):pass
 try:
  raw=json.loads((RUN/'aircraft.json').read_text());now=time.time()
  result['recent_aircraft']=sum(a.get('seen',999)+max(0,now-raw['now'])<60 for a in raw.get('aircraft',[])) if 0<=now-raw['now']<20 else None
 except (OSError,ValueError,KeyError,TypeError):result['recent_aircraft']=None
 return result

def history(before=0,include_history=True):
 result={'events':[],'aircraft':[],'next_before':None,'home':station.home(),'receiver':summary()['receiver'],'updated':None}
 raw=None
 try:
  candidate=json.loads((RUN/'aircraft.json').read_text())
  if 0<=time.time()-candidate['now']<10:raw=candidate
 except (OSError,ValueError,KeyError):pass
 if (DATA/'adsb.sqlite').exists():
  with closing(connect()) as db:
   db.row_factory=sqlite3.Row
   if include_history:
    rows=db.execute('SELECT * FROM events WHERE (?=0 OR id<?) ORDER BY id DESC LIMIT 101',(before,before)).fetchall();result['events']=[{**dict(r),'payload':json.loads(r['payload'])} for r in rows[:100]]
    if len(rows)>100:result['next_before']=rows[99]['id']
   if raw:
    cached={row['hex']:dict(row) for row in db.execute('SELECT * FROM positions WHERE received>?',(time.time()-300,))};result['aircraft']=live_aircraft(raw,cached,time.time());result['updated']=raw['now']
   else:
    cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=24)).isoformat();rows=db.execute('SELECT * FROM events WHERE id IN (SELECT max(id) FROM events WHERE received>? GROUP BY hex) ORDER BY id DESC LIMIT 500',(cutoff,)).fetchall()
    for r in rows:
     a=json.loads(r['payload']);a.update(received=r['received'],position_source='history',position_age=None)
     if valid_position(a):a['position_age']=max(0,time.time()-datetime.datetime.fromisoformat(r['received']).timestamp()+a.get('seen_pos',0))
     result['aircraft'].append(a)
 elif raw:result['aircraft']=live_aircraft(raw,{},time.time());result['updated']=raw['now']
 result['statistics']=summary();result['rf']=rf_stats();result['config']=load_config();result['recent_aircraft']=sum(a.get('seen',999)<60 for a in result['aircraft']) if result['updated'] else None;return result

def main():
 DATA.mkdir(parents=True,exist_ok=True);RUN.mkdir(parents=True,exist_ok=True);stop=False;previous=(0,{});last_prune=0;count=0;last=None
 def finish(*_):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
 with closing(connect()) as db:
  (RUN/'aircraft.json').unlink(missing_ok=True)
  native=subprocess.Popen(command(station.load()))
  try:
   while not stop:
    if native.poll() is not None:raise RuntimeError('dump1090 skončil: '+str(native.returncode))
    state={'updated':time.time(),'frequency':1090000000,'session_count':count,'last_received':last,'aircraft':0,'error':None,'config':load_config()}
    try:
     raw=json.loads((RUN/'aircraft.json').read_text())
     if time.time()-raw['now']<10:
      total,planes,delta=ingest(db,raw,previous);previous=(total,planes);count+=delta
      if delta:last=datetime.datetime.fromtimestamp(raw['now'],datetime.timezone.utc).isoformat()
      state.update(session_count=count,last_received=last,aircraft=sum(a.get('seen',999)<300 for a in raw.get('aircraft',[])))
    except FileNotFoundError:pass
    except (ValueError,KeyError,sqlite3.Error) as e:state['error']=str(e)
    rf=rf_stats()
    if rf:state['rf']={k:v for k,v in rf.items() if k!='raw'}
    station.atomic('adsb-state.json',state)
    if time.time()-last_prune>600:
     cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=7)).isoformat()
     for table in ('events','samples'):
      db.execute('DELETE FROM '+table+' WHERE received<?',(cutoff,));db.execute('DELETE FROM '+table+' WHERE id < coalesce((SELECT id FROM '+table+' ORDER BY id DESC LIMIT 1 OFFSET 99999),0)')
     db.execute('DELETE FROM positions WHERE received<?',(time.time()-86400,))
     db.commit();last_prune=time.time()
    for _ in range(10):
     if stop:break
     time.sleep(.5)
  finally:
   native.terminate()
   try:native.wait(timeout=5)
   except subprocess.TimeoutExpired:native.kill();native.wait()
if __name__=='__main__':main()
