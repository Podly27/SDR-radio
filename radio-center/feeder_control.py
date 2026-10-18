#!/usr/bin/python3
"""Restricted sudo helper: fixed feeder services, JSON stdin, no credential output."""
import json,os,re,runpy,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
UNITS={'adsbx':'adsbexchange-feed.service','fr24':'fr24feed.service'}
def systemctl(*args):
 return subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,text=True,timeout=15)
def values(path):
 try:text=Path(path).read_text()
 except (FileNotFoundError,PermissionError):return {}
 return dict(re.findall(r'^([\w-]+)\s*=\s*"?([^"\n]*)"?\s*$',text,re.M))
def status():
 result={}
 for name,unit in UNITS.items():
  result[name]={'active':systemctl('is-active',unit).stdout.strip()=='active','enabled':systemctl('is-enabled',unit).stdout.strip()=='enabled'}
 cfg=values('/etc/fr24feed.ini');result['fr24']['key_set']=bool(cfg.get('fr24key')) if cfg else None;result['fr24']['source']=cfg.get('host','127.0.0.1:30005')
 result['adsbx']['source']=values('/etc/default/adsbexchange').get('INPUT','127.0.0.1:30005')
 result['adsbx']['id_set']=Path('/usr/local/share/adsbexchange/adsbx-uuid').exists()
 result['adsbx']['connected']=False
 try:
  metrics=Path('/run/adsbexchange-feed/stats.prom')
  if time.time()-metrics.stat().st_mtime<90:
   result['adsbx']['connected']=any(float(value)>0 for value in re.findall(r'readsb_net_connector_status\{host="feed[12]?\.adsbexchange\.com",port="(?:30004|64004)"\} ([0-9.]+)',metrics.read_text()))
 except (OSError,ValueError):pass

 try:
  raw=json.loads(Path('/run/adsbexchange-feed/aircraft.json').read_text());fresh=time.time()-float(raw['now'])<15
  result['adsbx'].update(messages=raw.get('messages',0) if fresh else None,aircraft=len(raw.get('aircraft',[])) if fresh else None)
 except (OSError,ValueError,KeyError,TypeError):pass
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8754/monitor.json',timeout=2) as response:raw=json.load(response)
  # Explicit allowlist: the raw FR24 response also contains the sharing key.
  result['fr24'].update(key_set=bool(raw.get('fr24key')),connected=raw.get('feed_status')=='connected',receiver_connected=str(raw.get('rx_connected'))=='1',radar=str(raw.get('feed_alias','')),messages=raw.get('num_messages'),last_sent=raw.get('feed_last_ac_sent_time'),last_aircraft=raw.get('feed_last_ac_sent_num'))
 except (OSError,ValueError,TypeError):result['fr24']['connected']=False
 result['adsbx']['stats_active']=systemctl('is-active','adsbexchange-stats.service').stdout.strip()=='active'
 result['adsbx']['mlat_active']=systemctl('is-active','adsbexchange-mlat.service').stdout.strip()=='active'
 try:
  uid=Path('/usr/local/share/adsbexchange/adsbx-uuid').read_text().strip()
  if re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',uid):result['adsbx']['feed_uid']=uid
 except OSError:pass
 return result

def execute(payload):
 if payload=={'action':'status'}:return status()
 if set(payload)-{'action','adsbx_enabled','fr24_enabled','fr24key'} or payload.get('action')!='save':raise ValueError('Neplatná akce')
 for key in ('adsbx_enabled','fr24_enabled'):
  if type(payload.get(key)) is not bool:raise ValueError('Neplatné nastavení služby')
 key=payload.get('fr24key','')
 if not isinstance(key,str) or (key and not re.fullmatch(r'[A-Za-z0-9]{16}',key)):raise ValueError('Klíč FR24 musí mít 16 písmen nebo číslic')
 cfg=values('/etc/fr24feed.ini')
 if payload['fr24_enabled'] and not (key or cfg.get('fr24key')):raise ValueError('Nejprve vyplňte sharing key Flightradar24')
 if key:
  import grp
  configure=runpy.run_path(str(Path(__file__).with_name('configure-fr24.py')))['configure']
  path=Path('/etc/fr24feed.ini');text=configure(path.read_text() if path.exists() else '',key)
  fd,name=tempfile.mkstemp(prefix='.fr24-',dir='/etc')
  try:
   with os.fdopen(fd,'w') as out:
    os.fchown(out.fileno(),0,grp.getgrnam('fr24').gr_gid);os.fchmod(out.fileno(),0o640);out.write(text)
   os.replace(name,path)
  finally:
   if os.path.exists(name):os.unlink(name)
 for name,unit in UNITS.items():
  enabled=payload[name+'_enabled']
  command=systemctl('enable' if enabled else 'disable','--now',unit)
  if command.returncode:raise ValueError('Změna služby '+name+' selhala')
  if name=='adsbx':
   for dependent in ('adsbexchange-stats.service','adsbexchange-mlat.service'):
    if systemctl('show',dependent,'--property=LoadState','--value').stdout.strip()!='loaded':continue
    if enabled and dependent=='adsbexchange-mlat.service' and values('/etc/default/adsbexchange').get('USER','0') in ('0','disable'):continue
    if systemctl('enable' if enabled else 'disable','--now',dependent).returncode:raise ValueError('Změna související služby ADSBexchange selhala')
  if name=='fr24' and key and enabled:
   if systemctl('restart',unit).returncode:raise ValueError('Restart FR24 selhal')
 return status()
if __name__=='__main__':
 try:
  raw=sys.stdin.read(4097)
  if len(raw)>4096:raise ValueError('Příliš velký požadavek')
  print(json.dumps(execute(json.loads(raw))))
 except Exception as error:
  print(json.dumps({'error':str(error) if isinstance(error,ValueError) else 'Operace feederu selhala'}));sys.exit(1)
