"""EME station settings, topocentric Moon position, history and shared helpers."""
import datetime,json,math,os,re,sqlite3
from pathlib import Path
import ephem
import station_common
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
DEFAULT={'latitude':None,'longitude':None,'callsign':'','place':'','band':'70cm','starts':{'70cm':432000000,'2m':144100000},'minimum_elevation':15.0,'hysteresis':2.0,'mode':'off','device':'00000001','gain':40.2,'ppm':-7,'q65':['A','B','C'],'jt65':['B','C'],'strategy':'rotate','jt65_candidates':3}
WIDTH=90000
LIMITS={'70cm':(430000000,440000000),'2m':(144000000,146000000)}
def grid_location(grid):
 grid=grid.strip().upper()
 if not re.fullmatch(r'[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?',grid):raise ValueError('Neplatný Maidenhead lokátor (4, 6 nebo 8 znaků)')
 lon=-180+(ord(grid[0])-65)*20+int(grid[2])*2;lat=-90+(ord(grid[1])-65)*10+int(grid[3]);dx,dy=2,1
 if len(grid)>=6:dx,dy=2/24,1/24;lon+=(ord(grid[4])-65)*dx;lat+=(ord(grid[5])-65)*dy
 if len(grid)==8:dx/=10;dy/=10;lon+=int(grid[6])*dx;lat+=int(grid[7])*dy
 return lat+dy/2,lon+dx/2

def location_grid(lat,lon):
 x=min(lon+180,359.999999);y=min(lat+90,179.999999)
 a=int(x/20);b=int(y/10);x-=a*20;y-=b*10
 c=int(x/2);d=int(y);x-=c*2;y-=d
 return chr(65+a)+chr(65+b)+str(c)+str(d)+chr(65+min(23,int(x*12)))+chr(65+min(23,int(y*24)))

def number(value,lo,hi,label):
 if isinstance(value,bool):raise ValueError(label)
 try:value=float(value)
 except (TypeError,ValueError):raise ValueError(label)
 if not math.isfinite(value) or not lo<=value<=hi:raise ValueError(label)
 return value

def validate(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné nastavení')
 c=json.loads(json.dumps(DEFAULT));c.update(raw)
 if c.get('locator'):
  c['latitude'],c['longitude']=grid_location(c.pop('locator'))
 c['latitude']=number(c['latitude'],-90,90,'Zadej šířku −90 až 90°');c['longitude']=number(c['longitude'],-180,180,'Zadej délku −180 až 180°')
 if not isinstance(c['place'],str) or len(c['place'].strip())>80 or any(ord(x)<32 for x in c['place']):raise ValueError('Místo musí být text do 80 znaků')
 c['place']=c['place'].strip()
 c['callsign']=str(c['callsign']).strip().upper()
 if not re.fullmatch(r'[A-Z0-9/]{3,12}',c['callsign']):raise ValueError('Zadej identifikaci / značku (3–12 znaků)')
 if not isinstance(c['band'],str) or not isinstance(c['mode'],str) or c['band'] not in LIMITS or c['mode'] not in ('off','auto','manual'):raise ValueError('Neplatné pásmo nebo režim provozu')
 if not isinstance(c['starts'],dict) or set(c['starts'])!=set(LIMITS):raise ValueError('Neplatné přijímací úseky')
 for band,(lo,hi) in LIMITS.items():
  v=c['starts'][band]
  if isinstance(v,bool) or not isinstance(v,int) or v%1000 or not lo<=v<=hi-WIDTH:raise ValueError('Začátek úseku musí být v pásmu a v celých kHz')
 c['minimum_elevation']=number(c['minimum_elevation'],0,85,'Elevace musí být 0–85°')
 c['hysteresis']=number(c['hysteresis'],.5,5,'Hystereze musí být 0,5–5°')
 if c['minimum_elevation']+c['hysteresis']>=90:raise ValueError('Startovací elevace musí být pod 90°')
 c['gain']=number(c['gain'],0,49.6,'Zisk musí být 0–49,6 dB')
 c['ppm']=number(c['ppm'],-200,200,'Korekce musí být −200 až 200 ppm')
 if c['ppm']!=int(c['ppm']):raise ValueError('Korekce musí být celé ppm')
 c['ppm']=int(c['ppm'])
 if not isinstance(c['device'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',c['device']):raise ValueError('Neplatné sériové číslo SDR')
 for key,allowed in (('q65','ABCDE'),('jt65','ABC')):
  if not isinstance(c[key],list) or any(not isinstance(x,str) or len(x)!=1 or x not in allowed for x in c[key]) or len(c[key])!=len(set(c[key])):raise ValueError('Neplatné podrežimy')
 if not isinstance(c['strategy'],str) or c['strategy'] not in ('rotate','all'):raise ValueError('Neplatná strategie dekódování')
 if isinstance(c['jt65_candidates'],bool) or not isinstance(c['jt65_candidates'],int) or not 1<=c['jt65_candidates']<=5:raise ValueError('Počet JT65 kandidátů musí být 1–5')
 if not c['q65'] and not c['jt65']:raise ValueError('Vyber alespoň jeden podrežim')
 return {key:c[key] for key in DEFAULT}

def load_config():
 try:
  raw=json.loads((DATA/'eme-config.json').read_text())
  if (station_common.DATA/'station.json').exists():raw.update({k:v for k,v in station_common.load().items() if k in DEFAULT})
  raw['minimum_elevation']=station_common.minimum_elevation('moon',raw.get('minimum_elevation',DEFAULT['minimum_elevation']))
  return validate(raw)
 except FileNotFoundError:
  c=json.loads(json.dumps(DEFAULT));c['minimum_elevation']=station_common.minimum_elevation('moon',c['minimum_elevation']);return c

def atomic(name,value):
 tmp=DATA/(name+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));os.replace(tmp,DATA/name)

def moon_position(c,now=None):
 now=now or datetime.datetime.now(datetime.timezone.utc)
 obs=ephem.Observer();obs.lat=str(c['latitude']);obs.lon=str(c['longitude']);obs.elevation=station_common.load().get('height',0);obs.pressure=0;obs.date=now
 moon=ephem.Moon(obs);out={'azimuth':math.degrees(float(moon.az)),'elevation':math.degrees(float(moon.alt)),'distance_km':float(moon.earth_distance)*149597870.7,'utc':now.isoformat(),'locator':location_grid(c['latitude'],c['longitude'])}
 for name,threshold,event in (('next_start',c['minimum_elevation']+c['hysteresis'],'next_rising'),('next_stop',c['minimum_elevation'],'next_setting')):
  obs.horizon=str(threshold)
  out[name]=None
  for day in range(30):
   obs.date=now+datetime.timedelta(days=day)
   try:
    out[name]=getattr(obs,event)(ephem.Moon(),use_center=True).datetime().replace(tzinfo=datetime.timezone.utc).isoformat();break
   except (ephem.AlwaysUpError,ephem.NeverUpError):pass
 return out

def should_receive(mode,elevation,running,minimum,hysteresis):
 if mode=='off':return False
 if mode=='manual':return True
 return elevation>=minimum if running else elevation>=minimum+hysteresis

def connect():
 db=sqlite3.connect(DATA/'eme.sqlite',timeout=10);db.execute('PRAGMA journal_mode=WAL')
 db.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,received TEXT NOT NULL,slot TEXT NOT NULL,frequency REAL NOT NULL,band TEXT NOT NULL,mode TEXT NOT NULL,submode TEXT NOT NULL,snr INTEGER NOT NULL,dt REAL,message TEXT NOT NULL,raw TEXT NOT NULL,UNIQUE(slot,frequency,band,mode,submode,message))')
 return db

def prune(db):
 cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat();db.execute('DELETE FROM messages WHERE received<?',(cutoff,));db.execute('DELETE FROM messages WHERE id<=(SELECT id FROM messages ORDER BY id DESC LIMIT 1 OFFSET 99999)');db.commit()

def history(query):
 from urllib.parse import parse_qs
 params=parse_qs(query);before=max(0,int(params.get('before',['0'])[0]));search=params.get('q',[''])[0][:100]
 out={'events':[],'total':0,'next_before':None}
 if (DATA/'eme.sqlite').exists():
  with sqlite3.connect(f'file:{DATA}/eme.sqlite?mode=ro',uri=True,timeout=10) as db:
   out['total']=db.execute('SELECT count(*) FROM messages').fetchone()[0]
   rows=db.execute('SELECT id,received,slot,frequency,band,mode,submode,snr,dt,message,raw FROM messages WHERE (?=0 OR id<?) AND (length(?)=0 OR instr(lower(message),lower(?))>0) ORDER BY id DESC LIMIT 101',(before,before,search,search)).fetchall()
   cols=('id','received','slot','frequency','band','mode','submode','snr','dt','message','raw');out['events']=[dict(zip(cols,row)) for row in rows[:100]]
   if len(rows)>100:out['next_before']=rows[99][0]
 return out
