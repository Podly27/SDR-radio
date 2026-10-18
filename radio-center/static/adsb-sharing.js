'use strict';
const el=id=>document.getElementById(id);
let token='',loaded=false,busy=false,canEdit=false;
const count=value=>value==null?'—':Number(value).toLocaleString('cs-CZ');
function render(data){
 if(data.can_edit!==undefined)canEdit=data.can_edit;
 for(const name of ['adsbx','fr24']){
  const d=data[name];
  el(name+'-state').textContent=!d.active?'Odesílání je zastavené':d.connected?'Připojeno k serveru':'Služba běží · spojení se serverem nepotvrzené';
  el(name+'-source').textContent=d.source||'—';
  if(!loaded)el(name+'-enabled').checked=d.enabled;
 }
 el('adsbx-messages').textContent=count(data.adsbx.messages);
 el('adsbx-aircraft').textContent=count(data.adsbx.aircraft);
 el('adsbx-id').textContent=data.adsbx.feed_uid||(data.adsbx.id_set?'Nastaven automaticky':'Zatím nevytvořen');
 el('adsbx-stats').textContent=data.adsbx.stats_active?'Služba běží · ověřte registraci na serveru':'Není spuštěný · server nemusí zobrazit Feed UID';
 el('adsbx-mlat').textContent=data.adsbx.mlat_active?'Služba běží · synchronizaci ověřte na serveru':'Vypnuté';
 const statsLink=el('adsbx-stats-link');
 statsLink.hidden=!data.adsbx.feed_uid;
 if(data.adsbx.feed_uid)statsLink.href='https://www.adsbexchange.com/api/feeders/?feed='+encodeURIComponent(data.adsbx.feed_uid);
 el('fr24-radar').textContent=data.fr24.radar||'—';
 el('fr24-key-state').textContent=data.fr24.key_set===null?'Nelze ověřit při zastavené službě':data.fr24.key_set?'Klíč je uložený':'Klíč není nastavený';
 const stamp=Number(data.fr24.last_sent);
 el('fr24-last').textContent=stamp>0?new Date(stamp*1000).toLocaleString('cs-CZ',{timeZone:globalThis.radioTimeZone||'Europe/Prague'}):'Zatím nepotvrzeno';
 el('fr24-aircraft').textContent=count(data.fr24.last_aircraft);
 loaded=true;
}
function controls(disabled){for(const id of ['adsbx-enabled','fr24-enabled','fr24-key','sharing-save'])el(id).disabled=disabled||!canEdit;}
async function refresh(){
 if(busy)return;
 try{
  const response=await fetch('/control/api/adsb/feeders',{cache:'no-store'}),data=await response.json();
  if(!response.ok)throw Error(data.error||'Stav není dostupný');
  render(data);if(token)controls(false);
  if(!canEdit)el('sharing-message').textContent='Přehled je aktivní. Změny klíče a služeb čekají na povolení správy z webu.';
  else if(el('sharing-message').textContent==='Načítám stav…')el('sharing-message').textContent='Stav se obnovuje každých 10 sekund.';
 }catch(error){el('sharing-message').textContent=error.message+' · poslední zobrazené údaje nemusí být aktuální';controls(true);}
}
el('sharing-form').addEventListener('submit',async event=>{
 event.preventDefault();if(!token||busy||!canEdit)return;busy=true;controls(true);
 el('sharing-message').textContent='Ukládám nastavení…';
 try{
  const response=await fetch('/control/api/adsb/feeders',{method:'POST',headers:{'Content-Type':'application/json','X-Control-Token':token},body:JSON.stringify({adsbx_enabled:el('adsbx-enabled').checked,fr24_enabled:el('fr24-enabled').checked,fr24key:el('fr24-key').value.trim()})});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Uložení selhalo');
  loaded=false;render(data);el('fr24-key').value='';el('sharing-message').textContent='Sdílení dat je uložené.';
 }catch(error){el('sharing-message').textContent=error.message;}
 finally{busy=false;controls(false);}
});
fetch('/control/api/status',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{token=data.token;if(loaded)controls(false);}).catch(()=>{el('sharing-message').textContent='Ovládání není dostupné. Obnovte stránku.';});
refresh();setInterval(refresh,10000);
