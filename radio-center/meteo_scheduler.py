#!/usr/bin/python3
"""Meteor pass gate with durable SDR borrowing and return."""
import signal,subprocess,time
import meteo_common as common
import radio_lease as lease
RX='radio-meteo-rx.service'
def snapshot():
 states=lease.snapshot();return states.get(RX) in ('active','activating','deactivating'),[u for u in lease.active_receivers(states) if u!=RX]
def should_start(mode,running,others,orbit,now,synced=True):
 if running:return False
 return mode=='manual' or bool(synced and orbit.get('tle_fresh') and any(p['start']<=now<p['end'] for p in orbit.get('passes',[])))
def main():
 common.DATA.mkdir(parents=True,exist_ok=True);stop=False;last_request=None;attempted=False;manual_started=False;window_id=None;armed=lease.generation();completed=set()
 def finish(*_):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
 try:
  while not stop:
   state={'updated':time.time(),'receiver_running':False,'error':None}
   try:
    c=common.load_config();stat=(common.DATA/'meteo-config.json').stat();request=stat.st_mtime_ns
    if request!=last_request:last_request=request;attempted=False
    orbit=common.position_and_passes(c);running,others=snapshot();state.update(orbit=orbit,other_receivers=others,receiver_running=running)
    synced=subprocess.run(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True,timeout=4).stdout.strip()=='yes';state['time_synced']=synced;now=time.time();window=next((p for p in orbit['passes'] if p['start']<=now<p['end']),None);key=str(round(window['start'])) if window else None
    if key!=window_id:window_id=key;armed=lease.generation()
    if lease.owns('meteo') and (not running or not window):lease.release('meteo',failed=not running and lease.snapshot().get(RX)=='failed')
    if running:state['reason']='Příjem LRPT · potom se obnoví původní aplikace' if lease.owns('meteo') else 'Ruční příjem LRPT'
    elif c['mode']=='manual' and attempted:state['reason']='Ruční příjem dokončen';common.atomic('meteo-state.json',state);break
    elif c['mode']=='auto' and not synced:state['reason']='Čeká na synchronizaci systémového času'
    elif c['mode']=='auto' and not orbit['tle_fresh']:state['reason']='Zastaralé TLE; automatický příjem je blokovaný'
    elif not window and c['mode']=='auto':state['reason']='Čeká na přelet · při příjmu dočasně převezme SDR'
    elif key in completed:state['reason']='Příjem tohoto přeletu je dokončen'
    elif should_start(c['mode'],running,others,orbit,now,synced):
     duration=c['duration'] if c['mode']=='manual' else max(1,min(900,int(window['end']-now)));common.atomic('meteo-run.json',{'config':c,'duration':duration,'requested':now,'automatic':c['mode']=='auto'})
     if c['mode']=='manual':
      with lease.manual_selection(RX):lease.action('start',RX)
      attempted=True;manual_started=True;state.update(receiver_running=True,reason='Ruční příjem LRPT')
     else:
      ok,reason=lease.acquire('meteo','meteor-'+key,window['end'],armed);state.update(receiver_running=ok,reason=reason)
      if ok:completed.add(key)
    else:state['reason']='Automatika čeká'
    common.atomic('meteo-state.json',state)
   except Exception as exc:state.update(error=str(exc),reason='Automatika čeká; viz diagnostika');common.atomic('meteo-state.json',state)
   for _ in range(6):
    if stop:break
    time.sleep(.5)
 finally:
  try:
   if lease.owns('meteo'):lease.release('meteo')
   elif manual_started and snapshot()[0]:lease.action('stop',RX)
  except Exception as exc:print(exc,flush=True)
if __name__=='__main__':main()
