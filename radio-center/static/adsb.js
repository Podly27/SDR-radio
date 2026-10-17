'use strict';
const $=id=>document.getElementById(id),buttons=[...document.querySelectorAll('[data-action]')];
let token='',busy=false,before=0,next=null,points=[],centered=false,configured=false,statusCache=null,statusAt=0,lastHistoryAt=0;
const map=L.map('adsb-map').setView([49,15],6),markers=L.layerGroup().addTo(map),home=L.layerGroup().addTo(map),planeMarkers=new Map();let tileError=false;
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).on('tileerror',()=>{tileError=true;$('map-status').textContent='Mapový podklad není dostupný; dekódování a seznam letadel pokračují.';}).addTo(map);
if(typeof ResizeObserver!=='undefined')new ResizeObserver(()=>map.invalidateSize()).observe($('adsb-map'));
const n=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
const val=(v,unit='',digits=0)=>Number.isFinite(v)?v.toLocaleString('cs-CZ',{maximumFractionDigits:digits})+unit:'—';
const alt=a=>a.alt_baro==='ground'?'Na zemi':val((a.alt_baro??a.altitude)*.3048,' m');
const ident=a=>(a.flight?.trim()?a.flight.trim()+' · ':'')+a.hex.toUpperCase();
const located=a=>Number.isFinite(a.lat)&&Number.isFinite(a.lon)&&Math.abs(a.lat)<=90&&Math.abs(a.lon)<=180;
const ageText=seconds=>Number.isFinite(seconds)?seconds<60?Math.max(0,Math.floor(seconds))+' s':Math.floor(seconds/60)+' min '+Math.floor(seconds%60)+' s':'neznámé';
function signal(rssi){const good=Number.isFinite(rssi),level=!good?0:rssi< -30?1:rssi< -20?2:rssi< -10?3:4,badge=n('span'),bars=n('span');badge.className='ft-signal ft-level-'+level;bars.className='signal-bars';bars.setAttribute('aria-hidden','true');for(let i=1;i<=4;i++){const b=n('i');if(i<=level)b.className='lit';bars.append(b);}badge.append(bars,n('span',good?rssi.toFixed(1)+' dBFS':'Neznámý signál'));badge.title='Orientační RSSI, nikoli SNR';return badge;}
async function getStatus(){if(statusCache&&Date.now()-statusAt<5000)return statusCache;const r=await fetch('/control/api/status',{cache:'no-store'});if(!r.ok)throw Error('Stav přijímače není dostupný');statusCache=await r.json();statusAt=Date.now();return statusCache;}
function renderPlanes(h,live){
 points=[];home.clearLayers();const seen=new Set();let freshCount=0,oldCount=0;
 if(Number.isFinite(h.home.lat)&&Number.isFinite(h.home.lon)){L.circleMarker([h.home.lat,h.home.lon],{radius:7,color:'#e6a854',fillOpacity:1}).bindTooltip('Přijímač · '+h.home.place).addTo(home);if(!centered){map.setView([h.home.lat,h.home.lon],8);centered=true;}}
 const body=$('aircraft');body.replaceChildren();if(!h.aircraft.length)body.append(n('p','Zatím žádné letadlo v přehledu.'));
 for(const a of h.aircraft){
  const positionAge=a.position_age,show=located(a)&&(!live||(Number.isFinite(positionAge)&&positionAge<=300)),fresh=live&&Number.isFinite(positionAge)&&positionAge<60;
  const card=n('article');card.className='adsb-aircraft-row'+(show?' has-position':'');card.append(n('h3',ident(a)),n('p',alt(a)+' · '+val((a.gs??a.speed)*1.852,' km/h')+' · '+val(a.track,'°')),signal(a.rssi));
  const position=n('p',show?'Poloha před '+ageText(positionAge):'Bez přijaté polohy');position.className=fresh?'adsb-position-fresh':'adsb-position-old';card.append(position,n('p',live?'Poslední zpráva před '+ageText(a.seen):'Uloženo '+new Date(a.received).toLocaleString('cs-CZ',{timeZone:globalThis.radioTimeZone})));body.append(card);
  if(!show)continue;
  card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label','Zobrazit polohu '+ident(a));card.onclick=()=>{map.setView([a.lat,a.lon],10);planeMarkers.get(a.hex)?.openPopup();};card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();card.onclick();}};
  const popup=n('div');popup.append(n('strong',ident(a)),n('p',alt(a)+' · '+val((a.gs??a.speed)*1.852,' km/h')),n('p','Poloha před '+ageText(positionAge)+(a.position_source==='last_local'?' · poslední místní dekódování':'')));
  const icon=L.divIcon({className:'adsb-plane '+(fresh?'fresh':'stale'),html:'✈',iconSize:[28,28]});let marker=planeMarkers.get(a.hex);
  if(marker){marker.setLatLng([a.lat,a.lon]);marker.setIcon(icon);marker.setOpacity(fresh?1:.65);marker.setPopupContent(popup);marker.setTooltipContent(ident(a)+' · '+ageText(positionAge));}
  else{marker=L.marker([a.lat,a.lon],{icon,opacity:fresh?1:.65}).bindTooltip(ident(a)+' · '+ageText(positionAge)).bindPopup(popup).addTo(markers);planeMarkers.set(a.hex,marker);}
  seen.add(a.hex);points.push([a.lat,a.lon]);if(fresh)freshCount++;else oldCount++;
 }
 for(const [key,marker]of planeMarkers)if(!seen.has(key)){markers.removeLayer(marker);planeMarkers.delete(key);}
 if(!tileError)$('map-status').textContent=live?'Místní příjem · '+freshCount+' čerstvých poloh · '+oldCount+' posledních poloh do 5 min':'Uložená historie · nejde o aktuální letový provoz · '+points.length+' poloh';
}
async function refresh(){try{
 const [s,hr]=await Promise.all([getStatus(),fetch('/control/api/adsb/live',{cache:'no-store'})]);if(!hr.ok)throw Error('Data ADS-B nejsou dostupná');const h=await hr.json(),state=s.adsb_service.ActiveState,active=state==='active',live=active&&Number.isFinite(h.updated)&&Date.now()/1000-h.updated<10;token=s.token;globalThis.radioTimeZone=s.station.timezone;
 $('state').textContent=active?'ADS-B přijímá · 1090 MHz':state==='failed'?'Příjem skončil chybou':'ADS-B je zastaveno';for(const b of buttons)b.disabled=busy||(b.dataset.action==='start'?active:!active);
 $('messages').textContent=h.statistics.available?h.statistics.hour_count.toLocaleString('cs-CZ'):'—';$('planes').textContent=h.aircraft.length;$('planes-detail').textContent=live?h.recent_aircraft+' s příjmem do 60 s · seznam do 5 min':'Uložená historie za 24 hodin';$('last').textContent=h.statistics.last_received?new Date(h.statistics.last_received).toLocaleTimeString('cs-CZ',{timeZone:globalThis.radioTimeZone}):'Zatím žádná';
 const rf=h.rf;$('rf-status').textContent=active&&rf?val(rf.messages_per_second,' zpráv/s',1)+' · zisk '+val(rf.gain_db,' dB',1)+' · šum '+val(rf.noise_dbfs,' dBFS',1)+'\n'+val(rf.positions*60/rf.period_seconds,' poloh/min',1)+' · ztráta vzorků '+val(rf.drop_percent,' %',2):'Příjmové statistiky se objeví po spuštění ADS-B.';
 if(!configured){$('gain-mode').value=h.config.gain_mode;$('adsb-gain').value=h.config.gain??'';configured=true;}$('rf-save').disabled=busy;
 $('diagnostics').textContent=JSON.stringify({service:s.adsb_service,receiver:h.receiver,rf:h.rf,config:h.config,lease:s.radio_lease,station:s.station},null,2);renderPlanes(h,live);
 if($('history-panel').open&&before===0&&Date.now()-lastHistoryAt>15000)loadHistory();
 }catch(e){$('message').textContent=e.message;buttons.forEach(b=>b.disabled=true);}}
async function loadHistory(){try{const r=await fetch('/control/api/adsb/history?before='+before,{cache:'no-store'});if(!r.ok)throw Error('Historie není dostupná');const h=await r.json();lastHistoryAt=Date.now();next=h.next_before;$('older').hidden=next===null;$('empty').textContent=h.events.length?'':'Zatím žádné uložené dekódování ADS-B.';const body=$('history');body.replaceChildren();for(const e of h.events){const a=e.payload,tr=n('tr');tr.append(n('td',e.received.replace('T',' ').slice(0,19)),n('td',ident(a)),n('td',alt(a)),n('td',located(a)?a.lat.toFixed(4)+', '+a.lon.toFixed(4):'—'));body.append(tr);}}catch(e){$('empty').textContent=e.message;}}
async function post(path,payload){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Control-Token':token},body:JSON.stringify(payload)}),d=await r.json();if(!r.ok)throw Error(d.error);return d;}
buttons.forEach(b=>b.onclick=async()=>{if(b.disabled)return;const action=b.dataset.action;if(action==='start'&&!confirm('Spustit ADS-B na 1090 MHz a uvolnit RTL-SDR zastavením jiné aplikace?'))return;busy=true;buttons.forEach(b=>b.disabled=true);try{await post('/control/api/service',{service:'adsb',action,dashboard:true});statusCache=null;$('message').textContent='Změna provedena.';}catch(e){$('message').textContent=e.message;}finally{busy=false;refresh();}});
$('rf-settings').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;try{await post('/control/api/adsb/config',{gain_mode:$('gain-mode').value,gain:$('adsb-gain').value.trim()===''?null:Number($('adsb-gain').value)});$('message').textContent='Nastavení ADS-B uloženo. Pro použití nových hodnot restartuj přijímač.';}catch(e){$('message').textContent=e.message;}finally{busy=false;refresh();}};
$('fit').onclick=()=>{if(points.length)map.fitBounds(L.latLngBounds(points),{padding:[20,20],maxZoom:12});};$('latest').onclick=()=>{before=0;loadHistory();};$('older').onclick=()=>{before=next;loadHistory();};$('history-panel').addEventListener('toggle',()=>{if($('history-panel').open)loadHistory();});refresh();setInterval(()=>{if(!busy)refresh();},2000);
