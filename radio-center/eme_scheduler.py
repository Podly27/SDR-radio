#!/usr/bin/python3
"""Persistent Moon gate with shared receiver borrowing and automatic return."""
import datetime,json,signal,subprocess,time
import eme_common as common
import radio_lease as lease
RX='radio-eme-rx.service'
def snapshot():
 states=lease.snapshot();return states.get(RX) in ('active','activating'),[u for u in lease.active_receivers(states) if u!=RX]
def action(verb):lease.action(verb,RX)
def main():
 common.DATA.mkdir(parents=True,exist_ok=True);stopped=False;fingerprint=None;last_request=None;last_window=None;armed=lease.generation();last_attempt=0
 def finish(*_):
  nonlocal stopped
  stopped=True
 signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
 try:
  while not stopped:
   state={'updated':time.time(),'moon':None,'error':None,'receiver_running':False,'reason':'Načítám nastavení'}
   try:
    c=common.validate(common.load_config());stat=(common.DATA/'eme-config.json').stat();request=stat.st_mtime_ns;new_request=request!=last_request;last_request=request;state['config']=c;moon=common.moon_position(c);state['moon']=moon;running,others=snapshot();state.update(receiver_running=running,other_receivers=others)
    ntp=subprocess.run(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True,timeout=4).stdout.strip()=='yes';state['time_synced']=ntp
    current=json.dumps({k:v for k,v in c.items() if k not in ('mode','minimum_elevation','hysteresis','place')},sort_keys=True)
    desired=common.should_receive(c['mode'],moon['elevation'],running,c['minimum_elevation'],c['hysteresis']) and ntp
    if c['mode']=='auto':
     if not desired:
      lease.release('eme');last_window=None;state['reason']='Čekám na synchronizaci času NTP' if not ntp else 'Měsíc je pod startovacím limitem'
     else:
      expiry=datetime.datetime.fromisoformat(moon['next_stop']).timestamp();window='moon-'+moon['next_stop'][:13]
      if window!=last_window or (new_request and stat.st_mtime>=lease.read().get('manual_at',0)):last_window=window;armed=lease.generation()
      if lease.owns('eme') and not running:
       lease.release('eme',failed=True);state['reason']='Příjem skončil; původní aplikace se obnovuje'
      else:
       ok,reason=lease.acquire('eme',window,expiry,armed);state['reason']=reason;state['receiver_running']=ok
       if ok and fingerprint is not None and current!=fingerprint:lease.restart('eme')
    elif c['mode']=='off' or not ntp:
     if lease.owns('eme'):lease.release('eme')
     elif running:action('stop')
     state['reason']='Monitor je vypnutý' if c['mode']=='off' else 'Čekám na synchronizaci času NTP'
    else:
     # Explicit manual requests outrank automation; old requests never retake a new user selection.
     choice=lease.read();allowed=choice.get('manual_at',0)<=stat.st_mtime or choice.get('manual_target')==RX
     if new_request and allowed and (not running or lease.owns('eme')):
      with lease.manual_selection(RX):
       if not running:action('start')
     state['reason']='Ruční příjem bez omezení elevace' if snapshot()[0] else 'Ruční příjem zastaven jinou aplikací'
    fingerprint=current
   except Exception as exc:state['error']=str(exc);state['reason']='Automatika čeká; viz diagnostika'
   common.atomic('eme-scheduler.json',state)
   for _ in range(10):
    if stopped:break
    time.sleep(.5)
 finally:
  try:lease.release('eme')
  except Exception as exc:print(exc,flush=True)
if __name__=='__main__':main()
