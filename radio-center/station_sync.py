#!/usr/bin/python3
"""Restricted root helper: mirror validated station/SDR fields into OpenWebRX."""
import json,os,shutil,tempfile,time
from pathlib import Path
import station_common

def main():
 c=station_common.validate(station_common.load());p=Path('/var/lib/openwebrx/settings.json');s=json.loads(p.read_text());before=json.dumps(s,sort_keys=True)
 s['receiver_gps']={'lat':c['latitude'],'lon':c['longitude']};s['receiver_name']=c['callsign'];s['receiver_location']=c['place']
 for dev in s.get('sdrs',{}).values():
  if dev.get('type')!='rtl_sdr':continue
  dev.update(device=c['device'],ppm=c['ppm'],rf_gain=c['gain'])
  for profile in dev.get('profiles',{}).values():profile['rf_gain']=c['gain']
 if json.dumps(s,sort_keys=True)==before:return
 backup=Path('/opt/radio-center/backups/station');backup.mkdir(parents=True,exist_ok=True);shutil.copy2(p,backup/('settings-'+str(time.time_ns())+'.json'))
 st=p.stat();fd,tmp=tempfile.mkstemp(prefix='.station-',dir=p.parent)
 try:
  with os.fdopen(fd,'w') as out:json.dump(s,out,indent=4,ensure_ascii=False)
  os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,st.st_mode&0o777);os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
if __name__=='__main__':main()
