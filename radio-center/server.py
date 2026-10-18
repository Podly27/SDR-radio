#!/usr/bin/python3
"""Local radio service dashboard. Run as radio-center behind nginx."""
import datetime, json, os, secrets, shutil, subprocess, threading, time, sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from contextlib import closing, nullcontext
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).parent / 'static'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
SYSTEMCTL = '/usr/bin/systemctl'
from ft_profiles import PROFILES,metadata,validate_frequency,MSK_PROFILES,msk_metadata,validate_msk_frequency
from weak_profiles import PROFILES as WEAK_PROFILES,metadata as weak_metadata,validate_frequency as validate_weak_frequency
FT_PROFILES=tuple(PROFILES)
import eme_common
import dashboard_activity
import meteo_common
import radio_lease
import iss_auto
import station_common
import dashboard_layout
import adsb_worker
import feeder_control

def eme_status():
    result={}
    for key,name in (('receiver','eme-state.json'),('scheduler','eme-scheduler.json')):
        try:result[key]=json.loads((DATA/name).read_text())
        except (OSError,ValueError):result[key]=None
    try:result['config']=eme_common.load_config()
    except (ValueError,TypeError) as e:result['config']=eme_common.DEFAULT;result['error']=str(e)
    return result

def meteo_status():
    result={'config':meteo_common.load_config(),'runtime':None,'receiver':None,'orbit':None}
    for key,name in (('runtime','meteo-state.json'),('receiver','meteo-rx-state.json'),('diagnostic_plan','meteo-diagnostic-plan.json'),('diagnostic_summary','meteo-diagnostic-summary.json')):
        try:result[key]=json.loads((DATA/name).read_text())
        except (OSError,ValueError):pass
    result['processing_pending']=len(list((DATA/'meteo-process').glob('*.json')))
    try:result['orbit']=meteo_common.position_and_passes(result['config'])
    except (OSError,ValueError,KeyError) as e:result['error']=str(e)
    return result

def iss_auto_status():
    result={'config':iss_auto.load_config(),'profiles':iss_auto.PROFILES,'runtime':None,'orbit':None}
    try:result['runtime']=json.loads((DATA/'iss-auto-state.json').read_text())
    except (OSError,ValueError):pass
    try:result['orbit']=iss_auto.orbit()
    except (OSError,ValueError,KeyError) as e:result['error']=str(e)
    return result

from sonde_worker import TYPES as SONDE_TYPES,DEFAULT as SONDE_DEFAULT,validate_config as validate_sonde_config

STATE_LOCK=threading.Lock()
STATE_CACHE={}
STATE_AT=0

def service_snapshot():
    global STATE_CACHE,STATE_AT
    with STATE_LOCK:
        if time.monotonic()-STATE_AT<2:return STATE_CACHE
        r=subprocess.run([SYSTEMCTL,'list-units','--all','--type=service','--output=json','--no-pager'],capture_output=True,text=True,timeout=8)
        if r.returncode:raise RuntimeError('Nelze zjistit stavy služeb')
        wanted=['radio-adsb.service','radio-iss-auto.service','radio-return.service','radio-meteo.service','radio-meteo-rx.service','radio-iss.service','radio-eme.service','radio-eme-rx.service','openwebrx.service','radio-ism.service','radio-aprs.service','radio-lora.service','radio-vdl2.service','radio-sonde.service']+['radio-ft@'+p+'.service' for p in FT_PROFILES]+['radio-msk@'+p+'.service' for p in MSK_PROFILES]+['radio-weak@'+p+'.service' for p in WEAK_PROFILES]
        states={u:dict(Id=u,ActiveState='inactive',SubState='dead',MainPID='0') for u in wanted}
        for entry in json.loads(r.stdout):
            unit=entry['unit']
            if unit in states:
                states[unit]['ActiveState']=entry['active'];states[unit]['SubState']=entry['sub']
        active=[u for u,v in states.items() if v['ActiveState'] in ('active','activating','deactivating')]
        if active:
            r=subprocess.run([SYSTEMCTL,'show',*active,'--property=Id,MainPID'],capture_output=True,text=True,timeout=8)
            for block in r.stdout.strip().split('\n\n'):
                values=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
                if values.get('Id') in states:states[values['Id']]['MainPID']=values.get('MainPID','0')
        STATE_CACHE=states;STATE_AT=time.monotonic();return states

def service_state(unit='openwebrx.service'):
    return service_snapshot()[unit]

def ft_service_states(kind='ft'):
    profiles=FT_PROFILES if kind=='ft' else tuple(WEAK_PROFILES) if kind=='weak' else tuple(MSK_PROFILES)
    states=service_snapshot()
    return {p:states['radio-'+kind+'@'+p+'.service'] for p in profiles}

def ism_frequency():
    try:return json.loads((DATA/'ism-state.json').read_text()).get('frequency',433920000)
    except (OSError,ValueError):return 433920000

def sonde_config():
    try:
        c=json.loads((DATA/'sonde-tuning.json').read_text());return validate_sonde_config(c['type'],c['frequency'])
    except (OSError,ValueError,KeyError):return SONDE_DEFAULT.copy()

def dashboard_profile(kind):
    profiles=PROFILES if kind=='ft' else MSK_PROFILES
    running=next((p for p,state in ft_service_states(kind).items() if state['ActiveState']=='active'),None)
    if running:return running
    try:
        last=json.loads((DATA/(kind+'-state.json')).read_text()).get('profile')
        if last in profiles:return last
    except (OSError,ValueError,TypeError):pass
    return '2m-ft8' if kind=='ft' else '2m-msk144'

def status():
    mem = dict((k, int(v.split()[0])) for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()))
    usb = []
    for p in Path('/sys/bus/usb/devices').iterdir():
        try:
            if (p/'idVendor').read_text().strip() == '0bda' and (p/'idProduct').read_text().strip() in ('2832','2838'):
                usb.append({'port':p.name,'speed':(p/'speed').read_text().strip()})
        except OSError:
            continue
    try: temperature = int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
    except OSError: temperature = None
    disk = shutil.disk_usage('/')
    return {'service':service_state(), 'usb':usb, 'uptime':float(Path('/proc/uptime').read_text().split()[0]),
            'load':os.getloadavg()[0], 'cores':os.cpu_count(), 'memory_total':mem['MemTotal']//1024,
            'memory_used':(mem['MemTotal']-mem['MemAvailable'])//1024,
            'temperature':temperature, 'disk_used':round(disk.used/2**30,1), 'disk_total':round(disk.total/2**30,1),
            'hostname':os.uname().nodename, 'token':TOKEN, 'station':station_common.load(), 'layout':dashboard_layout.load(), 'adsb_service':service_state('radio-adsb.service'), 'adsb':adsb_worker.summary(), 'activity':dashboard_activity.summary(DATA,service_state()['ActiveState']=='active'), 'dashboard_profiles':{kind:dashboard_profile(kind) for kind in ('ft','msk')}, 'radio_lease':radio_lease.read(), 'radio_return_service':service_state('radio-return.service'), 'iss_auto_service':service_state('radio-iss-auto.service'), 'iss_auto':iss_auto_status(), 'meteo_service':service_state('radio-meteo.service'), 'meteo_rx_service':service_state('radio-meteo-rx.service'), 'meteo':meteo_status(), 'iss_service':service_state('radio-iss.service'), 'ism_service':service_state('radio-ism.service'), 'aprs_service':service_state('radio-aprs.service'), 'eme_service':service_state('radio-eme-rx.service'), 'eme_scheduler_service':service_state('radio-eme.service'), 'eme':eme_status(), 'weak_services':ft_service_states('weak'), 'weak_profiles':weak_metadata(), 'ft_services':ft_service_states(), 'ft_profiles':metadata(), 'msk_services':ft_service_states('msk'), 'msk_profiles':msk_metadata(), 'lora_service':service_state('radio-lora.service'), 'ism_frequency':ism_frequency(), 'vdl2_service':service_state('radio-vdl2.service'), 'sonde_service':service_state('radio-sonde.service'), 'sonde_config':sonde_config(), 'sonde_types':list(SONDE_TYPES)}

DATA = Path('/var/lib/radio-center')
def ism_history(query):
    params=parse_qs(query)
    before=max(0,int(params.get('before',['0'])[0]))
    search=params.get('q',[''])[0][:100]
    result={'events':[], 'total':0, 'devices':0, 'next_before':None}
    if (DATA/'ism.sqlite').exists():
        with sqlite3.connect(f'file:{DATA}/ism.sqlite?mode=ro',uri=True,timeout=10) as db:
            result['total']=db.execute('SELECT count(*) FROM events').fetchone()[0]
            result['devices']=db.execute('SELECT count(*) FROM (SELECT DISTINCT model,device FROM events)').fetchone()[0]
            rows=db.execute('SELECT id,received,model,device,payload FROM events WHERE (?=0 OR id<?) AND (length(?)=0 OR instr(lower(payload),lower(?))>0) ORDER BY id DESC LIMIT 101',(before,before,search,search)).fetchall()
            result['events']=[dict(id=r[0],received=r[1],model=r[2],device=r[3],payload=json.loads(r[4])) for r in rows[:100]]
            if len(rows)>100:result['next_before']=rows[99][0]
    try:result['receiver']=json.loads((DATA/'ism-state.json').read_text())
    except (OSError,ValueError):result['receiver']=None
    return result

def aprs_history(query,kind='aprs'):
    params=parse_qs(query);before=max(0,int(params.get('before',['0'])[0]));search=params.get('q',[''])[0][:100]
    result={'events':[],'positions':[],'total':0,'stations':0,'next_before':None}
    if (DATA/(kind+'.sqlite')).exists():
        with sqlite3.connect(f'file:{DATA}/{kind}.sqlite?mode=ro',uri=True,timeout=10) as db:
            result['total']=db.execute('SELECT count(*) FROM packets').fetchone()[0]
            result['stations']=db.execute('SELECT count(DISTINCT source) FROM packets').fetchone()[0]
            rows=db.execute('SELECT id,received,source,raw,payload FROM packets WHERE (?=0 OR id<?) AND (length(?)=0 OR instr(lower(raw),lower(?))>0) ORDER BY id DESC LIMIT 101',(before,before,search,search)).fetchall()
            result['events']=[dict(id=r[0],received=r[1],source=r[2],raw=r[3],payload=json.loads(r[4])) for r in rows[:100]]
            if len(rows)>100:result['next_before']=rows[99][0]
            cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=24)).isoformat()
            rows=db.execute('SELECT received,source,map_key,latitude,longitude,payload FROM packets WHERE id IN (SELECT max(id) FROM packets WHERE latitude IS NOT NULL AND received>? GROUP BY map_key) ORDER BY id DESC LIMIT 500',(cutoff,)).fetchall()
            result['positions']=[dict(received=r[0],source=r[1],name=r[2],lat=r[3],lon=r[4],payload=json.loads(r[5])) for r in rows if json.loads(r[5]).get('alive') is not False]
    try:result['receiver']=json.loads((DATA/(kind+'-state.json')).read_text())
    except (OSError,ValueError):result['receiver']=None
    result['home']=station_common.home()
    return result

def ft_history(query,kind='ft'):
    profiles=FT_PROFILES if kind=='ft' else tuple(WEAK_PROFILES) if kind=='weak' else tuple(MSK_PROFILES)
    params=parse_qs(query);before=max(0,int(params.get('before',['0'])[0]));search=params.get('q',[''])[0][:100];profile=params.get('profile',[''])[0]
    if profile and profile not in profiles:raise ValueError()
    band,mode=profile.split('-',1) if profile else ('','')
    result={'events':[],'total':0,'next_before':None}
    if (DATA/(kind+'.sqlite')).exists():
        with sqlite3.connect(f'file:{DATA}/{kind}.sqlite?mode=ro',uri=True,timeout=10) as db:
            result['total']=db.execute('SELECT count(*) FROM messages').fetchone()[0]
            rows=db.execute('SELECT id,received,slot,mode,band,dial,snr,dt,offset,message,raw FROM messages WHERE (?=0 OR id<?) AND (length(?)=0 OR instr(lower(message),lower(?))>0) AND (length(?)=0 OR (band=? AND mode=?)) ORDER BY id DESC LIMIT 101',(before,before,search,search,profile,band,mode)).fetchall()
            columns=('id','received','slot','mode','band','dial','snr','dt','offset','message','raw')
            result['events']=[dict(zip(columns,r)) for r in rows[:100]]
            if len(rows)>100:result['next_before']=rows[99][0]
    try:result['receiver']=json.loads((DATA/(kind+'-state.json')).read_text())
    except (OSError,ValueError):result['receiver']=None
    return result

def vdl2_history(query):
    params=parse_qs(query);before=max(0,int(params.get('before',['0'])[0]));search=params.get('q',[''])[0][:100];frequency=int(params.get('frequency',['0'])[0])
    if frequency not in (0,136725000,136775000,136875000,136975000):raise ValueError()
    result={'events':[],'total':0,'aircraft':0,'next_before':None}
    if (DATA/'vdl2.sqlite').exists():
        with sqlite3.connect(f'file:{DATA}/vdl2.sqlite?mode=ro',uri=True,timeout=10) as db:
            result['total']=db.execute('SELECT count(*) FROM frames').fetchone()[0]
            result['aircraft']=db.execute("SELECT count(DISTINCT aircraft) FROM frames WHERE aircraft!=''").fetchone()[0]
            rows=db.execute('SELECT id,received,frequency,source,destination,aircraft,registration,flight,message,kind,snr,payload FROM frames WHERE (?=0 OR id<?) AND (?=0 OR frequency=?) AND (length(?)=0 OR instr(lower(payload),lower(?))>0) ORDER BY id DESC LIMIT 101',(before,before,frequency,frequency,search,search)).fetchall()
            columns=('id','received','frequency','source','destination','aircraft','registration','flight','message','kind','snr','payload')
            for row in rows[:100]:
                e=dict(zip(columns,row));e['payload']=json.loads(e['payload']);result['events'].append(e)
            if len(rows)>100:result['next_before']=rows[99][0]
    try:result['receiver']=json.loads((DATA/'vdl2-state.json').read_text())
    except (OSError,ValueError):result['receiver']=None
    return result

def sonde_history(query):
    params=parse_qs(query);before=max(0,int(params.get('before',['0'])[0]));search=params.get('q',[''])[0][:100];serial=params.get('sonde',[''])[0][:64]
    result={'events':[],'flights':[],'track':[],'total':0,'next_before':None,'selected':serial}
    if (DATA/'sonde.sqlite').exists():
        with sqlite3.connect(f'file:{DATA}/sonde.sqlite?mode=ro',uri=True,timeout=10) as db:
            db.row_factory=sqlite3.Row
            result['total']=db.execute('SELECT count(*) FROM telemetry').fetchone()[0]
            cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=48)).isoformat()
            ids=db.execute('SELECT sonde,max(id) AS latest,min(received) AS first_seen,max(alt) AS max_alt,count(*) AS points FROM telemetry WHERE received>? GROUP BY sonde ORDER BY latest DESC LIMIT 50',(cutoff,)).fetchall()
            for row in ids:
                point=dict(db.execute('SELECT * FROM telemetry WHERE id=?',(row['latest'],)).fetchone());point.pop('fingerprint',None);point['payload']=json.loads(point['payload']);point.update(first_seen=row['first_seen'],max_alt=row['max_alt'],points=row['points']);result['flights'].append(point)
            if not serial and result['flights']:serial=result['flights'][0]['sonde']
            result['selected']=serial
            if serial:
                count=db.execute('SELECT count(*) FROM telemetry WHERE sonde=? AND received>? AND lat IS NOT NULL',(serial,cutoff)).fetchone()[0]
                step=max(1,(count+1997)//1998)
                rows=db.execute('WITH points AS (SELECT id,received,lat,lon,alt,temperature,humidity,pressure,speed,vertical,ROW_NUMBER() OVER (ORDER BY id) AS n FROM telemetry WHERE sonde=? AND received>? AND lat IS NOT NULL) SELECT * FROM points WHERE n=1 OR n=? OR n%?=0 ORDER BY n',(serial,cutoff,count,step)).fetchall()
                result['track']=[dict(row) for row in rows]
            rows=db.execute('SELECT * FROM telemetry WHERE (?=0 OR id<?) AND (length(?)=0 OR sonde=?) AND (length(?)=0 OR instr(lower(payload),lower(?))>0) ORDER BY id DESC LIMIT 101',(before,before,serial,serial,search,search)).fetchall()
            for row in rows[:100]:
                point=dict(row);point.pop('fingerprint',None);point['payload']=json.loads(point['payload']);result['events'].append(point)
            if len(rows)>100:result['next_before']=rows[99]['id']
    try:result['receiver']=json.loads((DATA/'sonde-state.json').read_text())
    except (OSError,ValueError):result['receiver']=None
    result['home']=station_common.home()
    return result

def clear_sonde_history():
    if not (DATA/'sonde.sqlite').exists():return 0
    with sqlite3.connect(DATA/'sonde.sqlite',timeout=10) as db:return db.execute('DELETE FROM telemetry').rowcount

def clear_vdl2_history():
    if not (DATA/'vdl2.sqlite').exists():return 0
    with sqlite3.connect(DATA/'vdl2.sqlite',timeout=10) as db:return db.execute('DELETE FROM frames').rowcount

def clear_ft_history(kind='ft'):
    if not (DATA/(kind+'.sqlite')).exists():return 0
    with sqlite3.connect(DATA/(kind+'.sqlite'),timeout=10) as db:
        count=db.execute('DELETE FROM messages').rowcount
    return count

def iss_history(query):
    params=parse_qs(query);before=int(params.get('before',['0'])[0])
    if before<0:raise ValueError()
    result={'events':[],'total':0,'next_before':None,'receiver':None}
    path=DATA/'iss.sqlite'
    if path.exists():
        with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=2)) as db:
            db.row_factory=sqlite3.Row;result['total']=db.execute('SELECT count(*) FROM images').fetchone()[0]
            rows=db.execute('SELECT * FROM images WHERE (?=0 OR id<?) ORDER BY id DESC LIMIT 25',(before,before)).fetchall()
            result['events']=[dict(row) for row in rows[:24]]
            if len(rows)>24:result['next_before']=rows[23]['id']
    try:result['receiver']=json.loads((DATA/'iss-state.json').read_text())
    except (OSError,ValueError):pass
    return result

def feeder_request(payload):
    result=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','/opt/radio-center/feeder_control.py'],input=json.dumps(payload),capture_output=True,text=True,timeout=90)
    try:data=json.loads(result.stdout)
    except ValueError:raise ValueError('Správa sdílení dat není dostupná')
    if result.returncode:raise ValueError(data.get('error','Změna selhala'))
    return data

class Handler(BaseHTTPRequestHandler):
    def respond(self, code, data, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path in ('/control/adsb', '/control/adsb/'):
            self.send_response(302)
            self.send_header('Location', '/adsbx/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path=='/control/api/adsb/feeders':
            try:
                data=feeder_control.status()
                data['can_edit']=Path('/opt/radio-center/feeder-edit-enabled').is_file()
                self.respond(200,data)
            except (ValueError,subprocess.TimeoutExpired):self.respond(503,{'error':'Stav sdílení dat není dostupný'})
            return
        if path=='/control/api/iss/audio':
            try:
                audio=Path('/run/radio-iss/audio.bin')
                if service_state('radio-iss.service')['ActiveState']!='active' or time.time()-audio.stat().st_mtime>3:raise FileNotFoundError()
                self.respond(200,audio.read_bytes(),'application/octet-stream')
            except OSError:self.respond(503,{'error':'Zvuk není dostupný; spusť přijímač ISS.'})
            return
        if path=='/control/api/iss/packets':
            try:self.respond(200,aprs_history(urlsplit(self.path).query,'iss-packet'))
            except ValueError:self.respond(400,{'error':'Neplatný filtr'})
            except (OSError,sqlite3.Error):self.respond(503,{'error':'Historie paketů není dostupná'})
            return
        if path=='/control/api/station':
            self.respond(200,station_common.load());return
        if path in ('/control/api/adsb/history','/control/api/adsb/live'):
            try:
                before=int(parse_qs(urlsplit(self.path).query).get('before',['0'])[0])
                if before<0:raise ValueError()
                self.respond(200,adsb_worker.history(before,include_history=path.endswith('/history')))
            except ValueError:self.respond(400,{'error':'Neplatný filtr'})
            except (OSError,sqlite3.Error):self.respond(503,{'error':'Historie ADS-B není dostupná'})
            return
        if path=='/control/api/status':
            try:self.respond(200,status())
            except (OSError,RuntimeError,subprocess.TimeoutExpired):self.respond(503,{'error':'Stav systému není nyní dostupný.'})
            return
        if path.startswith('/control/meteo/image/'):
            import re
            name=path.rsplit('/',1)[-1]
            if not re.fullmatch(r'[a-f0-9]{32}(?:-original)?\.png',name):self.respond(404,{'error':'Obrázek neexistuje.'});return
            try:self.respond(200,(DATA/'meteo-images'/name).read_bytes(),'image/png')
            except FileNotFoundError:self.respond(404,{'error':'Obrázek neexistuje.'})
            return
        if path.startswith('/control/iss/image/'):
            name=path.rsplit('/',1)[-1]
            import re
            if not re.fullmatch(r'(?:[a-f0-9]{32}|preview)\.png',name):self.respond(404,{'error':'Obrázek neexistuje.'});return
            try:self.respond(200,(DATA/'iss-images'/name).read_bytes(),'image/png')
            except FileNotFoundError:self.respond(404,{'error':'Obrázek neexistuje.'})
            return
        if path in ('/control/api/meteo/history','/control/api/iss/history','/control/api/ism/history','/control/api/aprs/history','/control/api/eme/history','/control/api/weak/history','/control/api/ft/history','/control/api/msk/history','/control/api/lora/history','/control/api/vdl2/history','/control/api/sonde/history'):
            try:
                query=urlsplit(self.path).query
                self.respond(200,meteo_common.history(query) if '/meteo/' in path else iss_history(query) if '/iss/' in path else eme_common.history(query) if '/eme/' in path else ft_history(query,'weak') if '/weak/' in path else sonde_history(query) if '/sonde/' in path else vdl2_history(query) if '/vdl2/' in path else aprs_history(query,'lora') if '/lora/' in path else ft_history(query,'msk') if '/msk/' in path else (ft_history if '/ft/' in path else aprs_history if '/aprs/' in path else ism_history)(query))
            except ValueError:self.respond(400,{'error':'Neplatný filtr.'})
            except (OSError,sqlite3.Error):self.respond(503,{'error':'Historie není dostupná.'})
            return
        files={'/control/adsb/sharing/':('adsb-sharing.html','text/html; charset=utf-8'), '/control/adsb-sharing.js':('adsb-sharing.js','text/javascript; charset=utf-8'), '/control/settings/':('settings.html','text/html; charset=utf-8'), '/control/settings.js':('settings.js','text/javascript; charset=utf-8'), '/control/shared.js':('shared.js','text/javascript; charset=utf-8'), '/control/adsb/receiver/':('adsb.html','text/html; charset=utf-8'), '/control/adsb.js':('adsb.js','text/javascript; charset=utf-8'), '/control/meteo.js':('meteo.js','text/javascript; charset=utf-8'), '/control/meteo/':('meteo.html','text/html; charset=utf-8'), '/control/iss.js':('iss.js','text/javascript; charset=utf-8'), '/control/iss/':('iss.html','text/html; charset=utf-8'), '/control/eme/':('eme.html','text/html; charset=utf-8'), '/control/eme.js':('eme.js','text/javascript; charset=utf-8'), '/control/weak/':('eme.html','text/html; charset=utf-8'), '/control/sonde/':('sonde.html','text/html; charset=utf-8'), '/control/sonde.js':('sonde.js','text/javascript; charset=utf-8'), '/control/vdl2/':('vdl2.html','text/html; charset=utf-8'), '/control/vdl2.js':('vdl2.js','text/javascript; charset=utf-8'), '/control/lora/':('lora.html','text/html; charset=utf-8'), '/control/msk/':('msk.html','text/html; charset=utf-8'), '/control/ft/':('ft.html','text/html; charset=utf-8'), '/control/ft.js':('ft.js','text/javascript; charset=utf-8'), '/control/aprs/':('aprs.html','text/html; charset=utf-8'), '/control/aprs.js':('aprs.js','text/javascript; charset=utf-8'), '/control/leaflet.js':('leaflet.js','text/javascript; charset=utf-8'), '/control/leaflet.css':('leaflet.css','text/css; charset=utf-8'), '/control/ism/':('ism.html','text/html; charset=utf-8'), '/control/ism.js':('ism.js','text/javascript; charset=utf-8'), '/' :('index.html','text/html; charset=utf-8'), '/control/':('index.html','text/html; charset=utf-8'),
               '/control/app.js':('app.js','text/javascript; charset=utf-8'), '/control/style.css':('style.css','text/css; charset=utf-8')}
        if path not in files:
            self.respond(404,{'error':'Stránka neexistuje.'});return
        name,mime=files[path]
        self.respond(200,(ROOT/name).read_bytes(),mime)

    def do_POST(self):
        if self.path not in ('/control/api/adsb/feeders','/control/api/adsb/config','/control/api/station','/control/api/layout','/control/api/iss-auto/config','/control/api/meteo/config','/control/api/service','/control/api/eme/config','/control/api/eme/clear','/control/api/weak/clear','/control/api/ft/clear','/control/api/msk/clear','/control/api/vdl2/clear','/control/api/sonde/clear'):self.respond(404,{'error':'Neznámá akce.'});return
        origin=self.headers.get('Origin')
        host=self.headers.get('Host','')
        if (origin and urlsplit(origin).netloc!=host) or self.headers.get('Sec-Fetch-Site')=='cross-site' or not secrets.compare_digest(self.headers.get('X-Control-Token',''),TOKEN):
            self.respond(403,{'error':'Obnov stránku a opakuj akci.'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096:raise ValueError()
            payload=json.loads(self.rfile.read(length))
            if self.path=='/control/api/adsb/feeders':
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna'});return
                try:
                    if not isinstance(payload,dict):raise ValueError('Neplatné nastavení')
                    self.respond(200,feeder_request({**payload,'action':'save'}))
                except ValueError as error:self.respond(400,{'error':str(error)})
                except subprocess.TimeoutExpired:self.respond(503,{'error':'Změna nedokončena; obnovte stav'})
                finally:LOCK.release()
                return
            if self.path=='/control/api/adsb/config':
                config=adsb_worker.validate_config(payload)
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna'});return
                try:station_common.atomic('adsb-config.json',config)
                finally:LOCK.release()
                self.respond(200,{'config':config});return
            if self.path in ('/control/api/station','/control/api/layout'):
                config=station_common.validate(payload) if self.path.endswith('station') else dashboard_layout.validate(payload)
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna'});return
                try:
                    station_common.atomic('station.json' if self.path.endswith('station') else 'dashboard-layout.json',config)
                    if self.path.endswith('station'):
                        result=subprocess.run(['/usr/bin/sudo','-n',SYSTEMCTL,'start','radio-station-sync.service'],capture_output=True,text=True,timeout=20)
                        if result.returncode:self.respond(503,{'error':'Stanoviště uloženo; synchronizace OpenWebRX selhala. Zkontroluj diagnostiku.'});return
                finally:LOCK.release()
                self.respond(200,{'config':config});return
            if self.path=='/control/api/iss-auto/config':
                config=iss_auto.validate(payload)
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna.'});return
                try:meteo_common.atomic('iss-auto-config.json',config)
                finally:LOCK.release()
                self.respond(200,{'config':config});return
            if self.path=='/control/api/meteo/config':
                config=meteo_common.validate(payload)
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna.'});return
                try:meteo_common.atomic('meteo-config.json',config)
                finally:LOCK.release()
                self.respond(200,{'config':config});return
            if self.path=='/control/api/eme/config':
                payload.update({k:v for k,v in station_common.load().items() if k in eme_common.DEFAULT});payload.pop('locator',None)
                config=eme_common.validate(payload)
                if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna.'});return
                try:
                    if config['mode']=='auto':radio_lease.rearm('eme')
                    eme_common.atomic('eme-config.json',config)
                finally:LOCK.release()
                self.respond(200,{'config':config});return
            if self.path=='/control/api/eme/clear':
                if payload.get('confirm')!='clear-eme-history':raise ValueError()
                count=0
                if (DATA/'eme.sqlite').exists():
                    with sqlite3.connect(DATA/'eme.sqlite',timeout=10) as db:count=db.execute('DELETE FROM messages').rowcount
                self.respond(200,{'deleted':count});return
            if self.path in ('/control/api/weak/clear','/control/api/ft/clear','/control/api/msk/clear','/control/api/vdl2/clear','/control/api/sonde/clear'):
                kind='weak' if '/weak/' in self.path else 'sonde' if '/sonde/' in self.path else 'vdl2' if '/vdl2/' in self.path else 'msk' if '/msk/' in self.path else 'ft'
                if not isinstance(payload,dict) or payload.get('confirm')!='clear-'+kind+'-history':raise ValueError()
                try:self.respond(200,{'deleted':clear_sonde_history() if kind=='sonde' else clear_vdl2_history() if kind=='vdl2' else clear_ft_history(kind)})
                except sqlite3.Error:self.respond(503,{'error':'Historii nyní nelze vymazat.'})
                return
            action=payload.get('action')
            target=payload.get('service','openwebrx')
            if target not in ('adsb','openwebrx','ism','aprs','ft','msk','weak','eme','lora','vdl2','sonde','iss','meteo','iss_auto'):raise ValueError()
            profile=payload.get('profile')
            if target in ('ft','msk') and profile is None:profile=dashboard_profile(target)
            if target=='weak' and profile not in WEAK_PROFILES:raise ValueError()
            if target=='ft' and profile not in FT_PROFILES:raise ValueError()
            if target=='msk' and profile not in MSK_PROFILES:raise ValueError()
            frequency=payload.get('frequency')
            sonde_tuning=None
            if target=='sonde' and action in ('start','restart'):
                current=sonde_config();sonde_tuning=validate_sonde_config(payload.get('sonde_type',current['type']),frequency if frequency is not None else current['frequency'])
            if target=='weak' and frequency is not None:validate_weak_frequency(profile,frequency)
            if target=='ft' and frequency is not None:validate_frequency(profile,frequency)
            if target=='msk' and frequency is not None:validate_msk_frequency(profile,frequency)
            if target=='ism' and frequency is not None and (isinstance(frequency,bool) or not isinstance(frequency,int) or frequency not in (433920000,868000000)):raise ValueError()
            unit={'adsb':'radio-adsb.service','iss_auto':'radio-iss-auto.service','meteo':'radio-meteo.service','iss':'radio-iss.service','openwebrx':'openwebrx.service','ism':'radio-ism.service','aprs':'radio-aprs.service','ft':'radio-ft@'+str(profile)+'.service','msk':'radio-msk@'+str(profile)+'.service','weak':'radio-weak@'+str(profile)+'.service','lora':'radio-lora.service','vdl2':'radio-vdl2.service','sonde':'radio-sonde.service','eme':'radio-eme-rx.service'}[target]
            if target=='iss' and action in ('stop','restart') and service_state('radio-iss-auto.service')['ActiveState']=='active':unit='radio-iss-auto.service'
            if action not in ('start','stop','restart'):raise ValueError()
        except (ValueError,AttributeError):self.respond(400,{'error':'Neplatná akce.'});return
        if not LOCK.acquire(blocking=False):self.respond(409,{'error':'Probíhá jiná změna služby.'});return
        try:
            if payload.get('dashboard') is True and action in ('stop','restart') and service_state(unit)['ActiveState']!='active':
                self.respond(409,{'error':'Aplikace nyní neběží. Obnov stav.'});return
            if target=='meteo' and action in ('start','restart'):
                config=meteo_common.load_config()
                if payload.get('meteo_mode') in ('auto','manual'):config['mode']=payload['meteo_mode']
                meteo_common.atomic('meteo-config.json',config)
            if target=='eme':
                config=eme_common.validate(eme_common.load_config())
                if action=='stop':config['mode']='off'
                elif action=='start':config['mode']='manual'
                eme_common.atomic('eme-config.json',config)
            if target in ('ft','msk','weak') and frequency is not None and action in ('start','restart'):
                path=DATA/(target+'-tuning.json')
                try:tuning=json.loads(path.read_text())
                except FileNotFoundError:tuning={}
                tuning[profile]=frequency;tmp=DATA/(target+'-tuning.tmp');tmp.write_text(json.dumps(tuning));os.replace(tmp,path)
            if target=='ism' and frequency is not None and action in ('start','restart'):
                tmp=DATA/'ism-tuning.tmp';tmp.write_text(json.dumps({'frequency':frequency}));os.replace(tmp,DATA/'ism-tuning.json')
                if action=='start' and service_state(unit)['ActiveState']=='active':action='restart'
            if sonde_tuning is not None:
                tmp=DATA/'sonde-tuning.tmp';tmp.write_text(json.dumps(sonde_tuning));os.replace(tmp,DATA/'sonde-tuning.json')
                if action=='start' and service_state(unit)['ActiveState']=='active':action='restart'
            if target=='iss' and action=='start' and service_state('radio-iss-auto.service')['ActiveState']=='active':
                stopped=subprocess.run(['/usr/bin/sudo','-n',SYSTEMCTL,'stop','radio-iss-auto.service'],capture_output=True,text=True,timeout=40)
                if stopped.returncode:raise RuntimeError('Automatiku ISS nelze zastavit')
            if unit=='radio-iss-auto.service' and action in ('start','restart'):
                radio_lease.rearm('iss')
                if service_state('radio-iss.service')['ActiveState']=='active' and not radio_lease.owns('iss'):
                    radio_lease.action('stop','radio-iss.service')
            if target=='meteo' and action in ('start','restart'):radio_lease.rearm('meteo')
            context=radio_lease.manual_selection(unit) if radio_lease.is_receiver(unit) and action in ('start','restart') else nullcontext()
            with context:
                result=subprocess.run(['/usr/bin/sudo','-n',SYSTEMCTL,action,unit],capture_output=True,text=True,timeout=40)
            if result.returncode:self.respond(503,{'error':'Změna služby selhala. Zkontroluj systémový log.'})
            else:
                global STATE_AT
                STATE_AT=0
                print('Service action:',action,unit,flush=True)
                self.respond(200,{'service':service_state(unit)})
        except (OSError,RuntimeError,subprocess.TimeoutExpired):self.respond(503,{'error':'Operace nedokončena; ověř aktuální stav služby.'})
        finally:LOCK.release()

if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8090),Handler).serve_forever()
