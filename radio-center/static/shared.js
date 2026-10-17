'use strict';
fetch('/control/api/station',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{globalThis.radioTimeZone=c.timezone;globalThis.radioStation=c;}).catch(()=>{});
document.addEventListener('DOMContentLoaded',()=>{const header=document.querySelector('body>header');if(header&&!location.pathname.startsWith('/control/settings')){const a=document.createElement('a');a.href='/control/settings/';a.textContent='⚙ Nastavení';a.className='settings-link';header.append(a);}});
