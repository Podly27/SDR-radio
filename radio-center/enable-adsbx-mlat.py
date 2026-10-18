#!/usr/bin/python3
"""Enable ADSBexchange MLAT using the confirmed global antenna location."""
import os,re,shutil,subprocess,time
from pathlib import Path
import station_common

def settings(station):
 c=station_common.validate(station)
 if c['latitude'] is None or c['longitude'] is None:raise ValueError('Chybí souřadnice antény')
 name=re.sub(r'[^A-Za-z0-9_-]','_',c['callsign']+'-'+c['place']).strip('_-') or 'radio-center'
 return {'USER':name,'LATITUDE':str(c['latitude']),'LONGITUDE':str(c['longitude']),'ALTITUDE':str(c['height'])+'m'}

def main():
 changes=settings(station_common.load());path=Path('/etc/default/adsbexchange');text=path.read_text()
 backup=Path('/opt/radio-center/backups')/('mlat-'+str(time.time_ns()));backup.mkdir(mode=0o700);shutil.copy2(path,backup/'adsbexchange')
 for key,value in changes.items():
  text=re.sub(r'^'+key+r'=.*$',key+'="'+value+'"',text,flags=re.M)
 path.write_text(text)
 subprocess.run(['systemctl','enable','--now','adsbexchange-mlat.service'],check=True)
 subprocess.run(['systemctl','restart','adsbexchange-mlat.service'],check=True)
 subprocess.run(['systemctl','restart','adsbexchange-feed.service'],check=True)
 print('MLAT uses the global antenna coordinates and height. Backup:',backup)
if __name__=='__main__':main()
