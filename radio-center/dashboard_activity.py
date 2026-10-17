"""Small cached dashboard summaries; decoded messages come from durable history."""
import datetime,json,sqlite3,threading,time
from pathlib import Path
from urllib.request import urlopen
DATABASES={'iss_packet':('iss-packet','packets'),'meteo':('meteo','images'),'iss':('iss','images'),'ft':('ft','messages'),'msk':('msk','messages'),'weak':('eme','messages'),'aprs':('aprs','packets'),'lora':('lora','packets'),'ism':('ism','events'),'sonde':('sonde','telemetry'),'vdl2':('vdl2','frames')}
CACHE={};CACHE_LOCK=threading.Lock()
def ensure_indexes(data):
 for name,table in DATABASES.values():
  path=Path(data)/(name+'.sqlite')
  if path.exists():
   with sqlite3.connect(path,timeout=10) as db:db.execute(f'CREATE INDEX IF NOT EXISTS dashboard_{table}_received ON {table}(received)')

def history_stats(data,now=None):
 now=now or datetime.datetime.now(datetime.timezone.utc);stamp=now.isoformat();cutoff=(now-datetime.timedelta(hours=1)).isoformat();result={}
 for key,(name,table) in DATABASES.items():
  row={'hour_count':0,'last_received':None,'available':True}
  path=Path(data)/(name+'.sqlite')
  if path.exists():
   try:
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=.3) as db:
     row['hour_count']=db.execute(f'SELECT count(*) FROM {table} WHERE received>=? AND received<=?',(cutoff,stamp)).fetchone()[0]
     last=db.execute(f'SELECT received FROM {table} WHERE received<=? ORDER BY received DESC LIMIT 1',(stamp,)).fetchone();row['last_received']=last[0] if last else None
   except (OSError,sqlite3.Error):row.update(hour_count=None,available=False,error='Historie není dostupná')
  result[key]=row
 return result

def summary(data,openwebrx_active=False):
 data=Path(data);cache_key=(str(data),openwebrx_active)
 with CACHE_LOCK:
  entry=CACHE.get(cache_key)
  if entry and time.monotonic()-entry[0]<10:stats={key:dict(value) for key,value in entry[1].items()}
  else:
   stats=history_stats(data);web={'hour_count':None,'last_received':None,'listeners':None,'tuning':None,'available':True}
   if openwebrx_active:
    try:
     with urlopen('http://127.0.0.1:8073/metrics.json',timeout=.7) as response:metrics=json.load(response)
     web['tuning']=metrics.get('radio_center_activity')
     users=metrics.get('openwebrx',{}).get('users')
     if isinstance(users,int) and not isinstance(users,bool) and users>=0:web['listeners']=users
    except (OSError,ValueError,TypeError):web['error']='Počet posluchačů není dostupný'
   stats['openwebrx']=web;CACHE[cache_key]=(time.monotonic(),{key:dict(value) for key,value in stats.items()})
 for key,(name,_) in DATABASES.items():
  try:
   state=json.loads((data/(name+'-state.json')).read_text())
   if not isinstance(state,dict):raise ValueError()
   stats[key]['receiver']={k:state[k] for k in ('updated','profile','frequency','mode','band','period','session_count','cycles','queue','last_cycle','decode_seconds','time_synced','errors','skipped','capture','current_pass','planned_q65','planned_jt65','frames','rejected','current_mode','lines','height','preview','audio_rms','stopped','kind','doppler_hz','doppler_enabled','doppler_error','tuned_frequency','range_velocity','reason','receiver_running','error') if k in state}
  except (OSError,ValueError):stats[key]['receiver']=None
 return stats

if __name__=='__main__':
 import sys
 if sys.argv[1:]==['--index']:ensure_indexes('/var/lib/radio-center')
