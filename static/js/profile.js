// Profile page: profile picture (upload / create your own / remove),
// display name and bio. Everything saves through PATCH /api/auth/profile/.
const token = localStorage.getItem('access');
if(!token) location.href = '/login/';
const $ = id => document.getElementById(id);
const esc = s => { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; };
const AV_COLORS = ['#2e4f3e','#3f6b4f','#274435','#466f57','#2f5d46','#39594a','#315c40','#527a5f'];
function colorFor(name){ let h=0; for(const ch of String(name||'?')) h=(h*31+ch.charCodeAt(0))>>>0; return AV_COLORS[h%AV_COLORS.length]; }
function mediaUrl(path){ if(!path) return null; return path + (path.includes('?')?'&':'?') + 'token=' + encodeURIComponent(token); }
function avatarHtml(username, avatar, cls=''){
  if(avatar) return `<img class="avatar ${cls}" src="${mediaUrl(avatar)}" alt="">`;
  const initials = (String(username||'?').replace(/[^a-zA-Z0-9]/g,'').slice(0,2) || '?').toUpperCase();
  return `<span class="avatar avatar-fallback ${cls}" style="background:${colorFor(username)}">${esc(initials)}</span>`;
}
let myUsername = '', myProfile = null, avColor = AV_COLORS[0], avEmoji = '';

async function patchProfile(formData){
  const r = await fetch('/api/auth/profile/', {method:'PATCH', headers:{Authorization:'Bearer '+token}, body: formData});
  const j = await r.json().catch(()=>({}));
  if(!r.ok){ alert('Could not save: ' + (j.detail || JSON.stringify(j))); return null; }
  myProfile = j; return j;
}
function refreshAvatar(){
  $('my-avatar').innerHTML = avatarHtml(myUsername, myProfile?.avatar ? myProfile.avatar + '?v=' + Date.now() : null, 'avatar-lg');
}

async function load(){
  const r = await fetch('/api/auth/me/', {headers:{Authorization:'Bearer '+token}});
  if(r.status === 401){ location.href = '/login/'; return; }
  const me = await r.json();
  myUsername = me.username;
  const pr = await fetch('/api/auth/profile/', {headers:{Authorization:'Bearer '+token}});
  myProfile = await pr.json();
  $('p-username').textContent = myProfile.display_name || me.username;
  $('p-email').textContent = me.email || '';
  $('p-verified').innerHTML = me.email_verified
    ? '<span class="verified-yes">✅ Email verified</span>'
    : '<span class="verified-no">⚠️ Email not verified — check your inbox, or resend from Settings</span>';
  $('p-display').value = myProfile.display_name || '';
  $('p-bio').value = myProfile.bio || '';
  refreshAvatar();
  // Avatar maker pickers
  $('av-colors').innerHTML = AV_COLORS.map(c=>`<button type="button" class="swatch" data-color="${c}" style="background:${c};width:34px;height:34px"></button>`).join('');
  document.querySelectorAll('#av-colors .swatch').forEach(s=>s.onclick = ()=>{
    avColor = s.dataset.color;
    document.querySelectorAll('#av-colors .swatch').forEach(x=>x.classList.toggle('sel', x === s));
  });
  document.querySelector('#av-colors .swatch')?.classList.add('sel');
  const emojis = ['😀','😎','🦊','🐼','🦁','🐸','🚀','⭐','🔥','🎧','🏏','⚽'];
  $('av-emojis').innerHTML = emojis.map(e=>`<span data-emoji="${e}">${e}</span>`).join('');
  document.querySelectorAll('#av-emojis span').forEach(s=>s.onclick = ()=>{
    avEmoji = avEmoji === s.dataset.emoji ? '' : s.dataset.emoji;
    document.querySelectorAll('#av-emojis span').forEach(x=>x.classList.toggle('sel', x.dataset.emoji === avEmoji));
  });
}
$('avatar-upload').addEventListener('change', async e=>{
  const file = e.target.files[0]; e.target.value = '';
  if(!file) return;
  const fd = new FormData(); fd.append('avatar_upload', file);
  if(await patchProfile(fd)){ refreshAvatar(); $('pic-msg').textContent = 'Picture updated'; }
});
$('avatar-remove').onclick = async ()=>{
  const fd = new FormData(); fd.append('clear_avatar', '1');
  if(await patchProfile(fd)){ refreshAvatar(); $('pic-msg').textContent = 'Picture removed'; }
};
$('av-create').onclick = ()=>{
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d');
  x.fillStyle = avColor; x.beginPath(); x.arc(128,128,128,0,7); x.fill();
  x.fillStyle = '#fff'; x.textAlign = 'center'; x.textBaseline = 'middle';
  if(avEmoji){ x.font = '130px system-ui, "Segoe UI Emoji", sans-serif'; x.fillText(avEmoji, 128, 136); }
  else {
    const initials = (myUsername.replace(/[^a-zA-Z0-9]/g,'').slice(0,2) || '?').toUpperCase();
    x.font = 'bold 104px system-ui, sans-serif'; x.fillText(initials, 128, 134);
  }
  c.toBlob(async blob=>{
    if(!blob) return alert('Could not create the picture in this browser.');
    const fd = new FormData(); fd.append('avatar_upload', new File([blob], 'my-avatar.png', {type:'image/png'}));
    if(await patchProfile(fd)){ refreshAvatar(); $('pic-msg').textContent = 'New picture set!'; }
  }, 'image/png');
};
$('p-save').onclick = async ()=>{
  const fd = new FormData();
  fd.append('display_name', $('p-display').value);
  fd.append('bio', $('p-bio').value);
  if(await patchProfile(fd)){
    $('p-username').textContent = $('p-display').value || myUsername;
    $('p-saved').textContent = 'Saved ✓';
    setTimeout(()=>$('p-saved').textContent = '', 2500);
  }
};
$('p-logout').onclick = ()=>{
  localStorage.removeItem('access'); localStorage.removeItem('refresh');
  location.href = '/login/';
};
load();
