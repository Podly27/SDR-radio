"""Meteor LRPT station settings, orbit prediction and image history."""
import datetime,json,math,os,re,sqlite3,threading,time,uuid
from pathlib import Path
from contextlib import closing
from urllib.request import Request,urlopen
import ephem
import station_common
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
SATELLITES={'M2-4':59051,'M2-3':57166}
ORBIT_SATELLITES={**SATELLITES,'ISS':25544}
DEFAULT={'satellite':'M2-4','frequency':137100000,'symbolrate':72000,'minimum_elevation':10.0,'mode':'auto','gain':40.2,'duration':600}
PLAN_CACHE={};PLAN_LOCK=threading.Lock()
def atomic(name,value):
 p=DATA/(name+'.'+uuid.uuid4().hex+'.tmp');p.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));os.replace(p,DATA/name)
def number(v,low,high):
 if isinstance(v,bool):raise ValueError('Neplatná číselná hodnota')
 try:v=float(v)
 except (TypeError,ValueError):raise ValueError('Neplatná číselná hodnota')
 if not math.isfinite(v) or not low<=v<=high:raise ValueError('Číselná hodnota je mimo rozsah')
 return v
def validate(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné nastavení')
 c=dict(DEFAULT);c.update(raw)
 if not isinstance(c['satellite'],str) or c['satellite'] not in SATELLITES or c['frequency'] not in (137100000,137900000) or c['symbolrate'] not in (72000,80000) or c['mode'] not in ('auto','manual'):raise ValueError('Neplatná družice, frekvence nebo režim')
 c['minimum_elevation']=number(c['minimum_elevation'],0,80);c['gain']=number(c['gain'],0,49.6);c['duration']=int(number(c['duration'],30,900))
 return {key:c[key] for key in DEFAULT}
def load_config():
 try:
  c=validate(json.loads((DATA/'meteo-config.json').read_text()))
  if (station_common.DATA/'station.json').exists():c['gain']=station_common.load()['gain']
  c['minimum_elevation']=station_common.minimum_elevation('satellite',c['minimum_elevation'])
  return c
 except FileNotFoundError:
  c=dict(DEFAULT);c['minimum_elevation']=station_common.minimum_elevation('satellite',c['minimum_elevation']);return c
def station():
 c=station_common.load()
 if c['latitude'] is None or c['longitude'] is None:raise ValueError('Nastav souřadnice ve společném nastavení')
 return {key:c[key] for key in ('latitude','longitude','place','callsign','height')}
def read_tle(satellite):
 d=json.loads((DATA/('meteo-tle-'+satellite+'.json')).read_text());sat=ephem.readtle(d['name'],d['line1'],d['line2']);epoch=sat._epoch.datetime().replace(tzinfo=datetime.timezone.utc).timestamp();d['epoch']=epoch
 if d['line1'][2:7].strip()!=str(ORBIT_SATELLITES[satellite]):raise ValueError('TLE patří jiné družici')
 return d,sat

def update_tles():
 DATA.mkdir(parents=True,exist_ok=True);errors=[]
 for name,norad in ORBIT_SATELLITES.items():
  success=False
  for url in (f'https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE',f'https://db.satnogs.org/api/tle/?norad_cat_id={norad}'):
   try:
    with urlopen(Request(url,headers={'User-Agent':'RadioCenter/1.0'}),timeout=15) as response:text=response.read(32768).decode()
    if 'satnogs' in url:
     obj=json.loads(text)[0];lines=[obj['tle0'].removeprefix('0 '),obj['tle1'],obj['tle2']]
    else:lines=[s.strip() for s in text.splitlines() if s.strip()]
    if len(lines)!=3 or lines[1][2:7].strip()!=str(norad):raise ValueError('Neplatná odpověď TLE')
    sat=ephem.readtle(*lines);epoch=sat._epoch.datetime().replace(tzinfo=datetime.timezone.utc).timestamp()
    if abs(time.time()-epoch)>7*86400:raise ValueError('Zdroj vrátil zastaralé TLE')
    atomic('meteo-tle-'+name+'.json',{'name':lines[0],'line1':lines[1],'line2':lines[2],'fetched':time.time(),'source':url});success=True;break
   except Exception as exc:errors.append(name+': '+str(exc))
  if not success:print('TLE update failed:',name,errors[-1],flush=True)
 if not any((DATA/('meteo-tle-'+name+'.json')).exists() for name in ORBIT_SATELLITES):raise RuntimeError('Nepodařilo se stáhnout TLE')
 return errors

def observer(c):
 o=ephem.Observer();o.lat=str(c['latitude']);o.lon=str(c['longitude']);o.elevation=c.get('height',0);o.pressure=0;return o

def crossing(o,sat,left,right,threshold,rising):
 for _ in range(22):
  mid=(left+right)/2;o.date=mid;sat.compute(o);above=math.degrees(float(sat.alt))>=threshold
  if above==rising:right=mid
  else:left=mid
 return (left+right)/2

def position_and_passes(c,now=None):
 now=time.time() if now is None else now;st=station();tle,sat=read_tle(c['satellite']);fresh=abs(now-tle['epoch'])<=7*86400;o=observer(st);o.date=ephem.Date(datetime.datetime.fromtimestamp(now,datetime.timezone.utc));sat.compute(o)
 result={'station':st,'azimuth':math.degrees(float(sat.az)),'elevation':math.degrees(float(sat.alt)),'range_km':sat.range/1000,'tle_epoch':tle['epoch'],'tle_fetched':tle['fetched'],'tle_fresh':fresh,'passes':[],'updated':now}
 key=(tuple(st.items()),c['satellite'],c['minimum_elevation'],tle['epoch'])
 with PLAN_LOCK:
  entry=PLAN_CACHE.get(key)
  if entry and now-entry[0]<60:passes=entry[1]
  else:
   passes=[];cursor=ephem.Date(datetime.datetime.fromtimestamp(now,datetime.timezone.utc))-20*ephem.minute
   for _ in range(35):
    o.date=cursor
    try:rise,azrise,peak,alt,settime,azset=o.next_pass(sat)
    except (ValueError,ephem.NeverUpError):break
    if rise is None or settime is None:break
    cursor=settime+ephem.minute
    if float(rise)-float(ephem.Date(datetime.datetime.fromtimestamp(now,datetime.timezone.utc)))>2:break
    if math.degrees(float(alt))<c['minimum_elevation']:continue
    start=crossing(o,sat,float(rise),float(peak),c['minimum_elevation'],True);end=crossing(o,sat,float(peak),float(settime),c['minimum_elevation'],False)
    epoch=lambda v:ephem.Date(v).datetime().replace(tzinfo=datetime.timezone.utc).timestamp()
    if epoch(end)<=now:continue
    passes.append({'start':epoch(start),'end':epoch(end),'peak':epoch(peak),'maximum_elevation':math.degrees(float(alt)),'rise_azimuth':math.degrees(float(azrise))})
    if len(passes)>=12:break
   PLAN_CACHE.clear();PLAN_CACHE[key]=(now,passes)
 result['passes']=[p for p in passes if p['end']>now];return result

def connect():
 db=sqlite3.connect(DATA/'meteo.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,received TEXT NOT NULL,capture TEXT NOT NULL,filename TEXT UNIQUE NOT NULL,original TEXT NOT NULL,label TEXT NOT NULL,satellite TEXT NOT NULL,frequency INTEGER NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS dashboard_images_received ON images(received)');db.commit();return db

def history(query=''):
 from urllib.parse import parse_qs
 before=int(parse_qs(query).get('before',['0'])[0])
 if before<0:raise ValueError('Neplatná stránka')
 result={'events':[],'total':0,'next_before':None}
 if (DATA/'meteo.sqlite').exists():
  with closing(connect()) as db:
   db.row_factory=sqlite3.Row;result['total']=db.execute('SELECT count(*) FROM images').fetchone()[0];rows=db.execute('SELECT * FROM images WHERE (?=0 OR id<?) ORDER BY id DESC LIMIT 25',(before,before)).fetchall();result['events']=[dict(row) for row in rows[:24]]
   if len(rows)>24:result['next_before']=rows[23]['id']
 return result

def prune():
 import shutil
 # Gallery originals and metadata are retained. Low disk space blocks new capture.
 # Raw working products are bounded independently of the gallery.
 work=DATA/'meteo-work'
 if work.exists():
  dirs=sorted((p for p in work.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True)
  total=0
  for i,p in enumerate(dirs):
   size=sum(f.stat().st_size for f in p.rglob('*') if f.is_file());total+=size
   if i>=3 or total>512*1024**2:shutil.rmtree(p)

if __name__=='__main__':
 import sys
 if '--update-tle' in sys.argv:print(json.dumps(update_tles(),ensure_ascii=False))
