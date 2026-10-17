'use strict';
const $=id=>document.getElementById(id);let token='',busy=false,before=0,next=null,events=[],frequencyReady=false;
const controls=['start','stop'].map($);
const when=t=>t?new Date(t).toLocaleString('cs-CZ',{timeZone:globalThis.radioTimeZone||'Europe/Prague'}):'Zatím žádná zpráva';
function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
const fields={temperature_C:['Teplota','°C','♨'],temperature_F:['Teplota','°F','♨'],humidity:['Vlhkost','%','◉'],wind_avg_km_h:['Vítr','km/h','↝'],wind_max_km_h:['Nárazy větru','km/h','↝'],wind_dir_deg:['Směr větru','°','↗'],rain_mm:['Srážky','mm','☂'],pressure_hPa:['Tlak','hPa','◴'],moisture:['Vlhkost půdy','%','◉'],battery_V:['Napětí baterie','V','▰'],light_lux:['Osvětlení','lx','☀'],uv:['UV index','','☀']};
const technical=new Set(['receiver_frequency','time','model','id','device','channel','protocol','mic','mod','freq','freq1','freq2','rssi','snr','noise']);
function num(v,digits=1){return typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('cs-CZ',{maximumFractionDigits:digits}):typeof v==='object'?JSON.stringify(v):String(v);}
function quality(snr){if(typeof snr!=='number'||!Number.isFinite(snr))return {level:0,label:'Kvalita neznámá',tone:'unknown'};return snr<6?{level:1,label:'Slabý signál',tone:'weak'}:snr<12?{level:2,label:'Střední signál',tone:'fair'}:snr<20?{level:3,label:'Dobrý signál',tone:'good'}:{level:4,label:'Silný signál',tone:'strong'};}
function renderEvent(e){
 const p=e.payload,card=node('article','panel event'),head=node('div','event-head'),identity=node('div');
 identity.append(node('h2','',e.model+(e.device?' · ID '+e.device:'')),node('p','note',when(e.received)));
 const q=quality(p.snr),signal=node('div','signal-quality '+q.tone),bars=node('span','signal-bars');bars.setAttribute('aria-hidden','true');
 for(let i=1;i<=4;i++)bars.append(node('i',i<=q.level?'lit':''));
 signal.append(bars,node('span','',q.label));signal.title='Orientační kvalita podle SNR: pod 6 dB slabá, 6–12 dB střední, 12–20 dB dobrá, od 20 dB silná. Nejde o kalibrované měření výkonu.';
 head.append(identity,signal);card.append(head);
 const layout=node('div','event-layout'),data=node('section','event-data'),tiles=node('div','reading-grid');data.append(node('h3','event-section-title','Dekódovaná data'));
 for(const [k,v]of Object.entries(p)){
  if(technical.has(k))continue;
  const f=fields[k],tile=node('div','reading');
  if(k==='battery_ok'){
   const ok=v===1||v===true||v==='1',low=v===0||v===false||v==='0';tile.classList.add('battery');tile.append(node('span','reading-label','▰ Baterie'),node('strong',ok?'battery-good':low?'battery-low':'',ok?'V pořádku':low?'Slabá':num(v))); 
  }else{tile.append(node('span','reading-label',f?f[2]+' '+f[0]:k.replaceAll('_',' ')),node('strong','',num(v)+(f&&f[1]?' '+f[1]:'')));}
  tiles.append(tile);
 }
 if(!tiles.childElementCount)tiles.append(node('p','note','Zpráva neobsahuje naměřené hodnoty.'));
 data.append(tiles);
 const radio=node('section','event-radio');radio.append(node('h3','event-section-title','Signál a kanál'));const dl=node('dl','radio-values');
 const items=[['receiver_frequency','Přijímací pásmo',' MHz',3],['channel','Kanál','',0],['freq','Frekvence',' MHz',3],['freq1','Frekvence 1',' MHz',3],['freq2','Frekvence 2',' MHz',3],['mod','Modulace','',0],['rssi','Úroveň RSSI',' dB (rel.)',1],['snr','Odstup SNR',' dB',1],['noise','Šum',' dB (rel.)',1],['protocol','Protokol','',0],['mic','Kontrola dat','',0]];
 for(const [key,label,unit,digits]of items){if(p[key]===undefined||p[key]===null)continue;let val=num(key==='receiver_frequency'?p[key]/1e6:p[key],digits)+unit;if(key==='mic')val=p[key]==='CRC'?'CRC':p[key]==='CHECKSUM'?'Kontrolní součet':String(p[key]);dl.append(node('dt','',label),node('dd','',val));}
 radio.append(dl,node('p','signal-note','Barvy vyjadřují orientační kvalitu podle SNR. RSSI a šum jsou relativní hodnoty přijímače, nikoli dBm.'));
 layout.append(data,radio);card.append(layout);
 const detail=node('details','raw-message');detail.append(node('summary','','Původní dekódovaná zpráva'),node('pre','',JSON.stringify(p,null,2)));card.append(detail);return card;
}

async function update(){try{const [sr,hr]=await Promise.all([fetch('/control/api/status'),fetch('/control/api/ism/history?before='+before+'&q='+encodeURIComponent($('query').value))]);if(!sr.ok||!hr.ok)throw Error('Data nejsou dostupná.');const s=await sr.json(),h=await hr.json();token=s.token;const active=s.ism_service.ActiveState==='active';if(!frequencyReady){$('frequency').value=String(h.receiver?.frequency||433920000);frequencyReady=true;}$('state').textContent=active?'ISM přijímá · '+((h.receiver?.frequency||433920000)/1e6).toLocaleString('cs-CZ')+' MHz':s.ism_service.ActiveState==='failed'?'Příjem selhal · viz diagnostika':'ISM je zastavený';$('start').disabled=busy||active&&Number($('frequency').value)===h.receiver?.frequency;$('stop').disabled=busy||!active;$('total').textContent=h.total;$('devices').textContent=h.devices;$('last').textContent=when(h.receiver?.last_received);const rf=h.receiver?.stats?.frames;$('rf-stats').textContent=`Vzorkování ${((h.receiver?.sample_rate||250000)/1000).toLocaleString('cs-CZ')} kS/s · zisk ${h.receiver?.gain_db??29} dB · automatický detekční práh · `+(rf?`detekováno ${rf.count} rámců, ${rf.fsk} FSK, ${rf.events} úspěšných událostí (poslední statistický interval)`:'čekám na první statistiky');$('logs').textContent=h.receiver?.logs?.join('\n')||'Zatím není dostupná.';$('updated').textContent='Aktualizováno '+new Date().toLocaleTimeString('cs-CZ');events=h.events;next=h.next_before;$('older').hidden=next===null;$('empty').textContent=events.length?'':h.total?'Filtru neodpovídá žádná zpráva.':active?'Čekám na první dekódované vysílání čidla.':'Spusť ISM pro příjem. Zatím nejsou uložené zprávy.';const container=$('events');container.replaceChildren();for(const e of events)container.append(renderEvent(e));}catch(e){$('message').textContent=e.message;controls.forEach(b=>b.disabled=true);}}
async function action(service,action){if(service==='ism'&&action==='start'&&!confirm('Spustit ISM a zastavit ostatní rádiové aplikace?'))return;if(service==='openwebrx'&&!confirm('Zastavit ISM a spustit OpenWebRX?'))return;busy=true;controls.forEach(b=>b.disabled=true);$('message').textContent='Přepínám přijímač…';try{const r=await fetch('/control/api/service',{method:'POST',headers:{'Content-Type':'application/json','X-Control-Token':token},body:JSON.stringify({service,action,frequency:service==='ism'&&action!=='stop'?Number($('frequency').value):undefined})});const d=await r.json();if(!r.ok)throw Error(d.error);$('message').textContent=service==='openwebrx'?'OpenWebRX se spouští.':action==='stop'?'ISM zastaven.':'ISM se spouští.';}catch(e){$('message').textContent=e.message;}finally{busy=false;await update();}}
$('frequency').onchange=()=>{$('start').disabled=busy;};
$('start').onclick=()=>action('ism','start');$('stop').onclick=()=>action('ism','stop');$('filter').onsubmit=e=>{e.preventDefault();before=0;update();};$('latest').onclick=()=>{before=0;update();};$('older').onclick=()=>{before=next;update();};$('export').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(events,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='ism-history.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};update();setInterval(()=>{if(!busy)update();},5000);
