"""Cross-process SDR borrowing with durable return state and manual override.

Only one automatic owner at a time. Existing automatic reception always wins.
"""
import contextlib,fcntl,json,os,re,subprocess,time,uuid
from pathlib import Path
DATA=Path(os.environ.get('RADIO_DATA','/var/lib/radio-center'))
OWNERS={'eme':'radio-eme-rx.service','meteo':'radio-meteo-rx.service','iss':'radio-iss.service'}
MONITORS={'eme':'radio-eme.service','meteo':'radio-meteo.service','iss':'radio-iss-auto.service'}
def is_receiver(unit):
 return unit in ('radio-adsb.service','openwebrx.service','radio-ism.service','radio-aprs.service','radio-lora.service','radio-sonde.service','radio-vdl2.service','radio-iss.service','radio-eme-rx.service','radio-meteo-rx.service') or bool(re.fullmatch(r'radio-(?:ft|msk|weak)@[A-Za-z0-9-]+\.service',unit))
def snapshot():
 p=subprocess.run(['/usr/bin/systemctl','list-units','--all','--type=service','--output=json','--no-pager'],capture_output=True,text=True,timeout=8);p.check_returncode()
 return {u['unit']:u['active'] for u in json.loads(p.stdout)}
def active_receivers(states):return [u for u,state in states.items() if is_receiver(u) and state in ('active','activating','deactivating')]
def action(verb,unit):
 if verb not in ('start','stop','restart') or not (is_receiver(unit) or (unit=='radio-meteo.service' and verb=='start')):raise ValueError('Invalid receiver action')
 p=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/systemctl',verb,unit],capture_output=True,text=True,timeout=60)
 if p.returncode:raise RuntimeError(p.stderr[-500:] or 'Receiver action failed')
def read():
 try:return json.loads((DATA/'radio-lease.json').read_text())
 except FileNotFoundError:return {'generation':0,'lease':None,'blocked':{},'events':[]}
def save(state,message=None):
 if message:
  state['events']=(state.get('events',[])+[{'time':time.time(),'message':message}])[-20:]
 state['updated']=time.time();tmp=DATA/('radio-lease.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False));os.replace(tmp,DATA/'radio-lease.json')
@contextlib.contextmanager
def locked(timeout=5):
 DATA.mkdir(parents=True,exist_ok=True)
 with (DATA/'radio-lease.lock').open('a') as fd:
  until=time.monotonic()+timeout
  while True:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    if time.monotonic()>=until:raise RuntimeError('Probíhá přepínání přijímače')
    time.sleep(.05)
  try:yield
  finally:fcntl.flock(fd,fcntl.LOCK_UN)
def generation():return read().get('generation',0)
def owns(owner):return (read().get('lease') or {}).get('owner')==owner

def acquire(owner,window,expires,armed_generation):
 if owner not in OWNERS or expires<=time.time():return False,'Příjmové okno již skončilo'
 with locked(1):
  state=read();lease=state.get('lease')
  if state.get('generation',0)!=armed_generation or state.get('blocked',{}).get(owner)==window:return False,'Ruční volba má přednost do dalšího příjmového okna'
  if lease:
   if lease['owner']==owner:return True,'Automatický příjem běží'
   return False,'Přednost má probíhající automatický příjem: '+lease['owner'].upper()
  active=active_receivers(snapshot());unit=OWNERS[owner]
  if unit in active:return False,'Tento přijímač již běží ručně'
  if len(active)>1:return False,'Více aktivních přijímačů; nelze bezpečně převzít SDR'
  previous=active[0] if active else None
  lease={'owner':owner,'unit':unit,'monitor':MONITORS[owner],'window':window,'expires':expires,'previous':previous,'started':time.time()};state['lease']=lease;save(state,'Přebírá '+owner.upper()+'; návrat: '+(previous or 'bez příjmu'))
  try:action('start',unit)
  except Exception:
   # Keep the journal until the return actually succeeds; the watchdog can retry.
   state['lease']['expires']=time.time();save(state,'Spuštění selhalo; připraven návrat');raise
  return True,'Automatický příjem · po skončení návrat na '+(previous or 'zastavený přijímač')

def _release(state,owner,failed=False):
 lease=state.get('lease')
 if not lease or lease['owner']!=owner:return
 active=active_receivers(snapshot());unit=lease['unit'];others=[u for u in active if u!=unit]
 if others:
  # A user or external controller selected another app. Never overwrite it.
  state['generation']=state.get('generation',0)+1;state.setdefault('blocked',{})[owner]=lease['window'];state['lease']=None;save(state,'Přijímač změněn mimo automatiku; návrat zrušen');return
 if failed:state.setdefault('blocked',{})[owner]=lease['window']
 state['lease']['returning']=True;save(state)
 if unit in active:action('stop',unit)
 # Another application can be started externally during a slow stop.
 if active_receivers(snapshot()):
  state['lease']=None;state['generation']=state.get('generation',0)+1;save(state,'Ruční volba během zastavování; návrat zrušen');return
 previous=lease.get('previous')
 if previous:action('start','radio-meteo.service' if previous=='radio-meteo-rx.service' else previous)
 state['lease']=None;save(state,'Příjem '+owner.upper()+' skončil; obnoveno '+(previous or 'bez příjmu'))
def release(owner,failed=False):
 with locked():_release(read(),owner,failed)

@contextlib.contextmanager
def manual_selection(unit=None):
 """Serialize an explicit RF start/restart with automatic acquisition."""
 with locked():
  state=read();lease=state.get('lease')
  if lease:state.setdefault('blocked',{})[lease['owner']]=lease['window']
  state['generation']=state.get('generation',0)+1;state['manual_at']=time.time();state['manual_target']=unit;state['lease']=None;save(state,'Ruční volba aplikace; automatický návrat zrušen')
  yield

def rearm(owner):
 with locked():
  state=read();state.setdefault('blocked',{}).pop(owner,None);save(state)
  return state.get('generation',0)

def restart(owner):
 with locked():
  state=read();current=state.get('lease')
  if current and current['owner']==owner:action('restart',current['unit'])

def maintain():
 with locked(1):
  state=read();lease=state.get('lease')
  if not lease:return
  units=snapshot();active=active_receivers(units)
  if lease['unit'] not in active or time.time()>=lease['expires'] or units.get(lease['monitor']) not in ('active','activating'):
   _release(state,lease['owner'],failed=lease['unit'] not in active)

if __name__=='__main__':
 import signal
 stopped=False
 def stop(*_):
  global stopped
  stopped=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 while not stopped:
  try:maintain()
  except Exception as exc:print('SDR return:',exc,flush=True)
  for _ in range(4):
   if stopped:break
   time.sleep(.5)
