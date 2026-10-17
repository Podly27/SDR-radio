"""Shared station and SDR settings; legacy EME settings seed first migration."""
import json,math,os,re,uuid
from pathlib import Path
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
KEYS=('latitude','longitude','place','callsign','height','device','gain','ppm','timezone','moon_minimum_elevation','satellite_minimum_elevation')
BASE={'latitude':None,'longitude':None,'place':'','callsign':'','height':0,'device':'0','gain':40.2,'ppm':-7,'timezone':'Europe/Prague','moon_minimum_elevation':15.0,'satellite_minimum_elevation':10.0}
def atomic(name,value):
 DATA.mkdir(parents=True,exist_ok=True);p=DATA/(name+'.'+uuid.uuid4().hex+'.tmp');p.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));os.replace(p,DATA/name)
def grid_location(grid):
 grid=grid.strip().upper()
 if not re.fullmatch(r'[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?',grid):raise ValueError('Neplatný Maidenhead lokátor')
 lon=-180+(ord(grid[0])-65)*20+int(grid[2])*2;lat=-90+(ord(grid[1])-65)*10+int(grid[3]);dx,dy=2,1
 if len(grid)>=6:dx,dy=2/24,1/24;lon+=(ord(grid[4])-65)*dx;lat+=(ord(grid[5])-65)*dy
 if len(grid)==8:dx/=10;dy/=10;lon+=int(grid[6])*dx;lat+=int(grid[7])*dy
 return lat+dy/2,lon+dx/2

def validate(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné nastavení stanoviště')
 c={**BASE,**raw}
 if c.get('locator'):c['latitude'],c['longitude']=grid_location(c['locator'])
 for k,low,high in [('latitude',-90,90),('longitude',-180,180),('height',-500,9000),('gain',0,49.6),('ppm',-200,200),('moon_minimum_elevation',0,84),('satellite_minimum_elevation',0,80)]:
  try:v=float(c[k])
  except (TypeError,ValueError):raise ValueError('Neplatná hodnota: '+k)
  if isinstance(c[k],bool) or not math.isfinite(v) or not low<=v<=high:raise ValueError('Hodnota mimo rozsah: '+k)
  c[k]=v
 if c['ppm']!=int(c['ppm']):raise ValueError('PPM musí být celé číslo')
 c['ppm']=int(c['ppm'])
 for k in ('place','callsign','device','timezone'):
  if not isinstance(c[k],str) or len(c[k])>80 or any(ord(x)<32 for x in c[k]):raise ValueError('Neplatný text: '+k)
  c[k]=c[k].strip()
 c['callsign']=c['callsign'].upper()
 if not re.fullmatch(r'[A-Z0-9/]{3,12}',c['callsign']):raise ValueError('Neplatná volací značka')
 if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',c['device']):raise ValueError('Neplatné sériové číslo SDR')
 try:ZoneInfo(c['timezone'])
 except (ZoneInfoNotFoundError,ValueError):raise ValueError('Neplatné časové pásmo')
 return {k:c[k] for k in KEYS}
def load():
 try:return validate(json.loads((DATA/'station.json').read_text()))
 except FileNotFoundError:
  try:legacy=json.loads((DATA/'eme-config.json').read_text())
  except FileNotFoundError:return dict(BASE)
  return validate({**BASE,**{k:legacy[k] for k in KEYS if k in legacy}})
def home():
 c=load();return {'lat':c['latitude'],'lon':c['longitude'],'place':c['place'],'callsign':c['callsign']}

def minimum_elevation(kind,fallback):
 # Existing installations retain application limits until global settings are saved.
 try:raw=json.loads((DATA/'station.json').read_text())
 except FileNotFoundError:return fallback
 key=kind+'_minimum_elevation'
 return validate(raw)[key] if key in raw else fallback
