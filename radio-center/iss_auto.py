#!/usr/bin/python3
"""ISS pass listening: a pass predicts visibility, never an SSTV transmission."""
import json,signal,subprocess,time
import meteo_common as common
import radio_lease as lease
PROFILES={
 'sstv-uhf':{'name':'SSTV UHF · Robot36 / VIS','frequency':437550000,'kind':'sstv'},
 'sstv-vhf':{'name':'SSTV VHF · automatický VIS','frequency':145800000,'kind':'sstv'},
 'voice-vhf':{'name':'Voice downlink VHF','frequency':145800000,'kind':'voice'},
 'repeater-uhf':{'name':'Voice repeater UHF downlink','frequency':437800000,'kind':'voice'},
 'packet-vhf':{'name':'Packet VHF · AFSK 1200','frequency':145825000,'kind':'packet'},
 'packet-uhf':{'name':'Packet UHF · AFSK 1200','frequency':437825000,'kind':'packet'},
}
DEFAULT={'minimum_elevation':10.0,'profile':'sstv-uhf','frequency':437550000,'doppler':True}
def validate(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné nastavení')
 c=dict(DEFAULT);c.update(raw);c['minimum_elevation']=common.number(c['minimum_elevation'],0,80)
 if 'profile' not in raw and 'frequency' in raw:
  if raw['frequency'] not in (145800000,437550000):raise ValueError('Neplatná frekvence ISS SSTV')
  c['profile']='sstv-vhf' if raw['frequency']==145800000 else 'sstv-uhf'
 if not isinstance(c['profile'],str) or c['profile'] not in PROFILES:raise ValueError('Neplatný profil ISS')
 if not isinstance(c['doppler'],bool):raise ValueError('Neplatná volba Dopplerovy korekce')
 c['frequency']=PROFILES[c['profile']]['frequency']
 return {k:c[k] for k in DEFAULT}
def doppler_shift(frequency,range_velocity):return -frequency*range_velocity/299792458.0
def tuning(c,now=None):
 import datetime,math,ephem
 now=time.time() if now is None else now
 result={'doppler_enabled':c['doppler'],'doppler_hz':0.0,'tuned_frequency':c['frequency'],'range_velocity':None,'doppler_error':None}
 if not c['doppler']:return result
 try:
  tle,sat=common.read_tle('ISS')
  if abs(now-tle['epoch'])>7*86400:raise ValueError('TLE starší než 7 dní; Doppler nepoužit')
  obs=common.observer(common.station());obs.date=ephem.Date(datetime.datetime.fromtimestamp(now,datetime.timezone.utc));sat.compute(obs);velocity=float(sat.range_velocity);shift=doppler_shift(c['frequency'],velocity)
  if not math.isfinite(shift) or abs(shift)>20000:raise ValueError('Neplatná Dopplerova korekce')
  result.update(doppler_hz=shift,tuned_frequency=c['frequency']+shift,range_velocity=velocity)
 except (OSError,ValueError,KeyError) as exc:result['doppler_error']=str(exc)
 return result
def load_config():
 try:c=validate(json.loads((common.DATA/'iss-auto-config.json').read_text()))
 except FileNotFoundError:c=dict(DEFAULT)
 c['minimum_elevation']=common.station_common.minimum_elevation('satellite',c['minimum_elevation'])
 return c
def orbit():return common.position_and_passes({'satellite':'ISS',**load_config()})
def main():
 stop=False;last_window=None;armed=lease.generation();completed=set()
 def finish(*_):
  nonlocal stop
  stop=True
 signal.signal(signal.SIGTERM,finish);signal.signal(signal.SIGINT,finish)
 try:
  while not stop:
   state={'updated':time.time(),'receiver_running':False,'error':None}
   try:
    plan=orbit();now=time.time();window=next((p for p in plan['passes'] if p['start']<=now<p['end']),None);key=str(round(window['start'])) if window else None
    if key!=last_window:last_window=key;armed=lease.generation()
    states=lease.snapshot();running=states.get('radio-iss.service') in ('active','activating','deactivating');synced=subprocess.run(['/usr/bin/timedatectl','show','-p','NTPSynchronized','--value'],capture_output=True,text=True,timeout=4).stdout.strip()=='yes';state.update(orbit=plan,receiver_running=running,time_synced=synced)
    if lease.owns('iss') and (not window or not synced or not running):lease.release('iss',failed=states.get('radio-iss.service')=='failed')
    if running:state['reason']='Automatický příjem ISS při přeletu · potom obnoví původní aplikaci' if lease.owns('iss') else 'ISS přijímač běží ručně'
    elif not synced:state['reason']='Čeká na synchronizaci času'
    elif not plan['tle_fresh']:state['reason']='Zastaralé TLE; automatický příjem je blokovaný'
    elif not window:state['reason']='Čeká na přelet ISS · vysílání není zaručeno'
    elif key in completed:state['reason']='Příjem tohoto přeletu dokončen'
    else:
     ok,reason=lease.acquire('iss','iss-'+key,window['end'],armed);state.update(receiver_running=ok,reason=reason)
     if ok:completed.add(key)
   except Exception as exc:state.update(error=str(exc),reason='ISS automatika čeká; viz diagnostika')
   common.atomic('iss-auto-state.json',state)
   for _ in range(6):
    if stop:break
    time.sleep(.5)
 finally:
  try:lease.release('iss')
  except Exception as exc:print(exc,flush=True)
if __name__=='__main__':main()
