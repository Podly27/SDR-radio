import json, collections, datetime, shutil, math
from pathlib import Path
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
settings=Path('/var/lib/openwebrx/settings.json')
shutil.copy2(settings,str(settings)+'.backup-'+stamp)
d=json.loads(settings.read_text());d['sdrs']['rtlsdr']['name']='RTL-SDR'
settings.write_text(json.dumps(d,ensure_ascii=False,indent=4)+'\n')
source='https://hearham.com/api/repeaters/v1'
rows=json.loads(Path('/tmp/hearham.json').read_text())
prefixes={'OK':('OK',),'OM':('OM',),'SP':('SR','SP','SQ'),'OE':('OE',),'DL':('DB0','DM0','DF0','DO0','DK0')}
selected=collections.defaultdict(list); counts=collections.Counter();seen=set()
lat=d['receiver_gps']['lat'];lon=d['receiver_gps']['lon']
def dist(r):
 a,b=math.radians(lat),math.radians(float(r['latitude']))
 v=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(math.radians(float(r['longitude'])-lon)/2)**2
 return round(6371*2*math.asin(min(1,math.sqrt(v))))
for r in rows:
 country=next((k for k,p in prefixes.items() if r['callsign'].upper().startswith(p)),None)
 f=int(r['frequency'])
 if not country or not r.get('operational') or not r.get('offset') or not (144000000<=f<=146000000 or 430000000<=f<=440000000):continue
 key=(r['callsign'],f,r['mode'],r['city'])
 if key in seen:continue
 seen.add(key);counts[country]+=1
 selected[f].append((dist(r),country,r))
bookmarks=[]
for f,entries in sorted(selected.items()):
 entries.sort(key=lambda x:x[0]); near=entries[0];r=near[2]
 names=', '.join(f'{c} {row["callsign"]} ({row["mode"]}, {distance} km)' for distance,c,row in entries[:3])
 if len(entries)>3:names+=f' +{len(entries)-3}'
 details=[]
 for distance,c,row in entries:
  details.append(f'{c} {row["callsign"]} | {row["city"]} | {row["mode"]} | {distance} km | TX {f/1e6:.6f} MHz | CTCSS/CC {row.get("encode", "")}')
 bookmarks.append(dict(name=names,frequency=f,modulation='nfm',description='Zdroj: '+source+'; import '+stamp[:8]+'. Pouze zaznamy oznacene jako provozni. NFM pro analogovy poslech; digitalni hlasove dekodery nejsou dostupne.\n'+'\n'.join(details)))
weak=[
 ('70cm FT8',432174000,'ft8','FT8 Activity: https://ft8activity.eu/rules/'),
 ('70cm FT4',432170000,'ft4','FT8 Activity: https://ft8activity.eu/rules/'),
 ('70cm MOON / EME Q65, JT65',432065000,'q65','EME centrum aktivity; JT65 lze zvolit rucne. https://wsjt.sourceforge.io/Operating_Procedures.pdf'),
 ('70cm Meteor scatter / MSK144',432370000,'msk144','Centrum aktivity meteor scatter dle IARU R1 VHF Handbook 10.02.'),
 ('70cm SSB / tropo DX',432200000,'usb','SSB centrum aktivity dle IARU R1.'),
 ('70cm CW',432050000,'cw','Telegrafni centrum aktivity dle IARU R1.'),
 ('70cm Microwave talkback',432350000,'usb','Koordinace mikrovlnnych spojeni dle IARU R1.'),
 ('70cm FM simplex volani',433500000,'nfm','FM volaci frekvence dle IARU R1.'),
 ('70cm APRS',432500000,'nfm','APRS frekvence dle IARU R1 VHF Handbook 10.02; pro dekodovani pouzij externi APRS dekoder.'),
]
for name,f,mode,desc in weak:
 b=dict(name=name,frequency=f,modulation=mode,description=desc,scannable=False)
 if mode in ('ft8','ft4','q65','msk144'):b['underlying']='usb'
 bookmarks.append(b)
# Keep these in the main bookmark file so they override packaged marks at identical frequencies.
p=Path('/var/lib/openwebrx/bookmarks.json')
shutil.copy2(p,str(p)+'.backup-'+stamp)
existing=json.loads(p.read_text() or '[]')
freqs={b['frequency'] for b in bookmarks}
existing=[b for b in existing if b['frequency'] not in freqs]
p.write_text(json.dumps(existing+bookmarks,ensure_ascii=False,indent=2)+'\n')
print('Prevodace podle zemi:',dict(counts))
print('Kanaly prevadecu:',len(selected),'Dalsi zalozky:',len(weak))
Path('/home/rpodolsky/OpenWebRX/repeater-import-summary.json').write_text(json.dumps(dict(source=source,imported_at=stamp,repeaters=dict(counts),channels=len(selected),bookmarks=len(weak)),indent=2)+'\n')
