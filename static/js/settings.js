// Settings page: theme (per device), chat background + privacy + account
// (saved to the profile, so they follow the account).
const token = localStorage.getItem('access');
if(!token) location.href = '/login/';
const $ = id => document.getElementById(id);
const H = {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'};
async function api(url, opts={}){ const r = await fetch(url, {headers: H, ...opts}); if(r.status === 401) location.href = '/login/'; return r.json(); }
async function patchProfile(formData){
  const r = await fetch('/api/auth/profile/', {method:'PATCH', headers:{Authorization:'Bearer '+token}, body: formData});
  const j = await r.json().catch(()=>({}));
  if(!r.ok){ alert('Could not save: ' + (j.detail || JSON.stringify(j))); return null; }
  return j;
}

// --- Theme toggle (this device only) ---
const isDark = (document.documentElement.dataset.theme || 'dark') !== 'light';
$('theme-toggle').checked = isDark;
$('theme-toggle').addEventListener('change', e=>{
  const theme = e.target.checked ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try{ localStorage.setItem('theme', theme); }catch(_){}
});

// --- Chat background (saved to the account) ---
const WP_PRESETS = [
  {key:'default', label:'Default', css:''},
  {key:'ocean', label:'Ocean', css:'linear-gradient(160deg,#0ea5e9,#1e3a8a)'},
  {key:'sunset', label:'Sunset', css:'linear-gradient(160deg,#f59e0b,#db2777)'},
  {key:'forest', label:'Forest', css:'linear-gradient(160deg,#16a34a,#134e4a)'},
  {key:'grape', label:'Grape', css:'linear-gradient(160deg,#8b5cf6,#312e81)'},
  {key:'dots', label:'Dots', css:'radial-gradient(circle at 1px 1px, rgba(148,163,184,.35) 1.5px, transparent 0)'},
];
let wpChoice = '';
function markPreset(){
  document.querySelectorAll('#wp-presets .swatch').forEach(s=>s.classList.toggle('sel', wpChoice === 'preset:' + s.dataset.key));
}
async function saveWallpaperChoice(choice){
  wpChoice = choice; markPreset();
  const fd = new FormData(); fd.append('chat_wallpaper', choice);
  await patchProfile(fd);
}
$('wp-presets').innerHTML = WP_PRESETS.map(p=>
  `<button type="button" class="swatch" data-key="${p.key}" title="${p.label}" style="background:${p.css || 'var(--panel2)'}"></button>`).join('')
  + `<small style="align-self:center">presets</small>`;
document.querySelectorAll('#wp-presets .swatch').forEach(s=>s.onclick = ()=>saveWallpaperChoice(s.dataset.key === 'default' ? '' : 'preset:' + s.dataset.key));
$('wp-color').addEventListener('change', e=>saveWallpaperChoice('color:' + e.target.value));
$('wp-upload').addEventListener('change', async e=>{
  const file = e.target.files[0]; e.target.value = '';
  if(!file) return;
  const fd = new FormData(); fd.append('wallpaper_upload', file); fd.append('chat_wallpaper', 'image');
  if(await patchProfile(fd)){ wpChoice = 'image'; markPreset(); }
});
$('wp-reset').onclick = async ()=>{
  const fd = new FormData(); fd.append('clear_wallpaper', '1');
  if(await patchProfile(fd)){ wpChoice = ''; markPreset(); }
};

// --- Privacy switches ---
const PV = [['pv-online','show_online_status'], ['pv-lastseen','show_last_seen'],
            ['pv-receipts','send_read_receipts'], ['pv-discoverable','discoverable'],
            ['pv-email','show_email']];
async function loadPrivacy(){
  const p = await api('/api/auth/privacy/');
  for(const [id, key] of PV){
    $(id).checked = !!p[key];
    $(id).addEventListener('change', async e=>{
      await api('/api/auth/privacy/', {method:'PATCH', body: JSON.stringify({[key]: e.target.checked})});
    });
  }
}

// --- Account ---
async function loadAccount(){
  const me = await api('/api/auth/me/');
  $('s-account').innerHTML = `Signed in as <b>@${me.username}</b> · ${me.email || ''} · ` +
    (me.email_verified ? '<span class="verified-yes">✅ Email verified</span>'
                       : '<span class="verified-no">⚠️ Email not verified</span>');
  if(!me.email_verified) $('s-resend-row').hidden = false;
  const prof = await api('/api/auth/profile/');
  wpChoice = prof.chat_wallpaper || '';
  if(wpChoice.startsWith('color:')) $('wp-color').value = wpChoice.slice(6);
  markPreset();
}
$('s-resend').onclick = async ()=>{
  const me = await api('/api/auth/me/');
  const r = await fetch('/api/auth/resend-verification/', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({email: me.email})});
  const j = await r.json().catch(()=>({}));
  $('s-resend-msg').textContent = j.detail || 'Sent';
};
$('s-changepw').onclick = async ()=>{
  const cur = $('s-cur').value, next = $('s-new').value;
  if(!cur || !next) return;
  const r = await fetch('/api/auth/change-password/', {method:'POST', headers: H,
    body: JSON.stringify({current_password: cur, new_password: next})});
  const j = await r.json().catch(()=>({}));
  $('s-pwmsg').textContent = r.ok ? 'Password changed ✓' : ('Could not change: ' + (j.detail || r.status));
  $('s-pwmsg').style.color = r.ok ? '' : 'var(--danger)';
  if(r.ok){ $('s-cur').value = ''; $('s-new').value = ''; }
};
$('s-logout').onclick = ()=>{
  localStorage.removeItem('access'); localStorage.removeItem('refresh');
  location.href = '/login/';
};
loadPrivacy(); loadAccount();
