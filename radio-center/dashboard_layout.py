import json
import station_common as station
KEYS=('openwebrx','ft','weak','msk','aprs','lora','ism','sonde','vdl2','adsb','iss','meteo')
def validate(raw):
 if not isinstance(raw,dict):raise ValueError('Neplatné rozložení')
 order=raw.get('order');hidden=raw.get('hidden',[])
 if not isinstance(order,list) or not isinstance(hidden,list) or any(not isinstance(k,str) or k not in KEYS for k in order+hidden) or len(set(order))!=len(order) or len(set(hidden))!=len(hidden):raise ValueError('Neplatné pořadí nebo viditelnost')
 return {'order':order+[k for k in KEYS if k not in order],'hidden':hidden}
def load():
 try:return validate(json.loads((station.DATA/'dashboard-layout.json').read_text()))
 except FileNotFoundError:return {'order':list(KEYS),'hidden':[]}
