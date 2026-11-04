// Minimal but complete client: REST for history, WebSocket for live events.
const token = localStorage.getItem('access');
if(!token) location.href = '/login/';
const H = {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'};
let ws = null, currentConv = null, meId = null, typingTimer = null;
let replyToId = null, currentConvData = null, otherUserId = null;
const EMOJIS = ['😀','😂','🤣','😊','😍','😎','🤔','😮','😢','😡','👍','👎','🙏','👏','🔥','❤️','💯','🎉','✅','👋','🍕','☕','🚀','⭐','💡','📎','📷','🎵','⚽','🌟'];
const $ = id => document.getElementById(id);
const esc = s => { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; };

async function api(url, opts={}){ const r = await fetch(url,{headers:H,...opts}); if(r.status===401){location.href='/login/';} return r.json(); }

// --- Avatars: real photo if the user has one, else a coloured initials disc ---
const AV_COLORS = ['#2e4f3e','#3f6b4f','#274435','#466f57','#2f5d46','#39594a','#315c40','#527a5f'];
function colorFor(name){ let h=0; for(const ch of String(name||'?')) h=(h*31+ch.charCodeAt(0))>>>0; return AV_COLORS[h%AV_COLORS.length]; }
function mediaUrl(path){ if(!path) return null; return path + (path.includes('?')?'&':'?') + 'token=' + encodeURIComponent(token); }
function avatarHtml(username, avatar, cls=''){
  if(avatar) return `<img class="avatar ${cls}" src="${mediaUrl(avatar)}" alt="">`;
  const initials = (String(username||'?').replace(/[^a-zA-Z0-9]/g,'').slice(0,2) || '?').toUpperCase();
  return `<span class="avatar avatar-fallback ${cls}" style="background:${colorFor(username)}">${esc(initials)}</span>`;
}
function avatarWithDot(username, avatar, online, cls=''){
  return `<span class="avatar-wrap">${avatarHtml(username, avatar, cls)}${online?'<span class="online-dot"></span>':''}</span>`;
}
let myUsername = '', myProfile = null;
async function loadMe(){
  const me = await api('/api/auth/me/');
  meId = me.id; myUsername = me.username; myProfile = me.profile || {};
  $('me').textContent = me.username;
  const w = $('me-wrap'); w.querySelector('.avatar')?.remove();
  w.insertAdjacentHTML('afterbegin', avatarHtml(me.username, myProfile.avatar));
  const sm = $('side-me-avatar'); if(sm) sm.innerHTML = avatarHtml(me.username, myProfile.avatar);
  initWallpaper(myProfile);
  updateInfoPanel();
}
let allConvs = [], convFilter = 'all';
function fmtConvTime(iso){
  if(!iso) return '';
  const d = new Date(iso), now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if(sameDay) return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  const yest = new Date(now); yest.setDate(now.getDate()-1);
  if(d.toDateString() === yest.toDateString() || (now - d) < 7*24*3600*1000)
    return d.toLocaleDateString([], {weekday:'short'});
  return d.toLocaleDateString([], {day:'numeric', month:'short'});
}
function convPreview(c){
  const lm = c.last_message;
  if(!lm) return 'No messages yet';
  const when = fmtConvTime(lm.created_at);
  let txt;
  if(lm.is_deleted) txt = 'Message unsent';
  else if((lm.attachments||[]).some(a=>a.is_audio)) txt = '🎤 Voice message';
  else if(lm.kind === 'location') txt = lm.sender === meId ? 'You sent a location' : `${lm.sender_username} sent a location`;
  else if((lm.attachments||[]).length) txt = '📎 ' + (lm.attachments[0].original_name || 'Attachment');
  else txt = lm.body || '';
  if(c.type === 'group' && lm.sender !== meId && lm.kind !== 'location' && !(lm.attachments||[]).some(a=>a.is_audio))
    txt = `${lm.sender_username}: ${txt}`;
  return when ? `${txt} · ${when}` : txt;
}
function renderActiveRow(){
  const row = $('active-row'); if(!row) return;
  const priv = allConvs.filter(c=>c.type==='private');
  row.innerHTML = `<button type="button" class="active-item" data-new="1"><span class="new-disc">+</span><small>New</small></button>` +
    priv.map(c=>{
      const other = c.memberships.find(m=>m.user!==meId);
      const name = other?.username || 'Chat';
      return `<button type="button" class="active-item" data-id="${c.id}">${avatarWithDot(name, other?.avatar, !!other?.is_online)}<small>${esc(name.split(' ')[0])}</small></button>`;
    }).join('');
  row.querySelector('[data-new]')?.addEventListener('click', ()=>$('user-search').focus());
  row.querySelectorAll('[data-id]').forEach(el=>el.onclick=()=>openConv(+el.dataset.id));
}
function renderConvList(){
  let list = allConvs;
  if(convFilter === 'unread') list = list.filter(c=>c.unread_count > 0);
  if(convFilter === 'groups') list = list.filter(c=>c.type === 'group');
  $('conversations').innerHTML = list.map(c=>{
    const other = c.memberships.find(m=>m.user!==meId);
    const name = c.title || (other?.username || 'Chat');
    const av = c.type==='group'
      ? `<span class="avatar-wrap"><span class="avatar avatar-fallback">👥</span></span>`
      : avatarWithDot(other?.username || name, other?.avatar, !!other?.is_online);
    return `<div class="conv ${c.id===currentConv?'active':''}" data-id="${c.id}">${av}
      <span class="conv-main"><span class="conv-line"><strong>${esc(name)}</strong>${c.unread_count?`<span class="badge">${c.unread_count}</span>`:''}</span>
      <small>${esc(convPreview(c))}</small></span>${c.unread_count?'<span class="unread-dot"></span>':''}</div>`;}).join('')
      || '<p style="color:var(--muted);padding:8px">No conversations here yet.</p>';
  document.querySelectorAll('.conv').forEach(el=>el.onclick=()=>openConv(+el.dataset.id));
  renderActiveRow();
}
async function loadConvs(){
  const data = await api('/api/chat/conversations/');
  allConvs = data.results || data;
  renderConvList();
}
async function openConv(id){
  currentConv = id; ws?.close(); replyToId = null; $('reply-bar').hidden = true;
  document.body.classList.add('chat-open');  // mobile: switch from list view to chat view
  currentConvData = await api(`/api/chat/conversations/${id}/`);
  const others = (currentConvData.memberships||[]).filter(m=>m.user!==meId);
  otherUserId = currentConvData.type==='private' && others.length ? others[0].user : null;
  $('chat-header').textContent = currentConvData.title || (others[0]?.username || 'Conversation');
  $('block-btn').style.display = otherUserId ? '' : 'none';
  const data = await api(`/api/chat/messages/?conversation=${id}`);
  currentMsgs = data.results || data; msgFilter = null;
  document.querySelectorAll('.info-row').forEach(r=>r.classList.remove('active'));
  renderMsgList(currentMsgs);
  updateInfoPanel();
  await api('/api/chat/messages/mark_conversation_read/', {method:'POST', body: JSON.stringify({conversation:id})});
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/chat/${id}/?token=${token}`);
  ws.onmessage = e=>{
    const d = JSON.parse(e.data);
    if(d.type==='chat_message'){
      const nm = {id:d.message_id, sender:d.sender_id, sender_username:d.sender_username, body:d.body, attachments:d.attachments||[], kind:d.kind, latitude:d.latitude, longitude:d.longitude, location_live_until:d.location_live_until, created_at:d.created_at};
      currentMsgs.push(nm);
      if(!msgFilter) { $('messages').insertAdjacentHTML('beforeend', renderMsg(nm)); scrollDown(); }
      else if(msgMatchesFilter(nm)) renderMsgList(currentMsgs.filter(msgMatchesFilter));
      updateInfoPanel();
    }
    if(d.type==='location_updated'){
      const card = document.querySelector(`[data-loc-msg="${d.message_id}"]`);
      if(card){
        const lat = Number(d.latitude), lng = Number(d.longitude);
        card.href = `https://www.google.com/maps?q=${lat},${lng}`;
        const coords = card.querySelector('.loc-coords'); if(coords) coords.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
        const st = card.querySelector('.loc-state');
        if(st && d.stopped) st.innerHTML = 'Live location ended';
      }
    }
    if(d.type==='typing'){ $('typing').textContent = d.is_typing ? `${d.username} is typing…` : ''; }
    if(d.type==='presence'){
      allConvs.forEach(c=>c.memberships.forEach(m=>{ if(m.user===d.user_id) m.is_online = d.is_online; }));
      if(currentConvData) currentConvData.memberships.forEach(m=>{ if(m.user===d.user_id) m.is_online = d.is_online; });
      if(d.user_id === otherUserId){
        const label = d.is_online ? 'Active now' : 'Offline';
        $('chat-status').textContent = label; $('info-status').textContent = label;
        updateInfoPanel();
      }
      renderConvList();
    }
    if(d.type==='read_receipt'){ document.querySelector(`[data-msg="${d.message_id}"] small`)?.append(' ✓✓'); }
  };
  loadConvs();
}
function fileUrl(a){
  // Attachment downloads are authenticated; <img>/<a> tags cannot send the
  // Authorization header, so the token travels as a query parameter (the
  // same pattern as the WebSocket URL). Legacy /media/ links keep working.
  const u = a.file || '';
  if(u.startsWith('/api/chat/attachments/') && !u.includes('token='))
    return u + (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
  return u;
}
function renderAttachment(a){
  const name = a.original_name || (a.file||'').split('/').pop() || 'file';
  const url = fileUrl(a);
  if(a.is_audio){
    const bars = [10,18,24,14,22,9,17,25,12,20,15,23,11,19,13,21].map(h=>`<i style="height:${h}px"></i>`).join('');
    return `<span class="voice-note"><span class="play-look">▶</span><span class="waveform">${bars}</span><audio controls preload="metadata" src="${url}"></audio></span><br><a href="${url}" target="_blank" download>${esc(name)}</a>`;
  }
  return a.is_image
    ? `<a href="${url}" target="_blank"><img src="${url}" alt="${esc(name)}"></a>`
    : `<a href="${url}" target="_blank" download>📄 ${esc(name)}</a>`;
}
function renderLocation(m){
  const lat = Number(m.latitude), lng = Number(m.longitude);
  const maps = `https://www.google.com/maps?q=${lat},${lng}`;
  const until = m.location_live_until ? new Date(m.location_live_until) : null;
  const live = until && until > new Date();
  const state = until ? (live ? `<span class="loc-live">🔴 Live location · until ${until.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span>`
                               : 'Live location ended') : 'Location';
  return `<a class="loc-card" data-loc-msg="${m.id}" href="${maps}" target="_blank" rel="noopener">
    📍 <span class="loc-state">${state}</span><br>
    <small><span class="loc-coords">${lat.toFixed(5)}, ${lng.toFixed(5)}</span> · Open in Maps ↗</small></a>`;
}
function renderBody(m){
  // Rescue messages sent by the old client, which stored a file share as plain
  // text like "Shared a file: /media/attachments/.../name.pdf" - make it clickable.
  const legacy = (m.body||'').match(/^Shared an? (image|file):\s*(\/\S+)$/);
  if(legacy && !(m.attachments||[]).length){
    const url = legacy[2], name = decodeURIComponent(url.split('/').pop());
    const isImg = /\.(jpe?g|png|gif|webp)$/i.test(url);
    return renderAttachment({file:url, original_name:name, is_image:isImg});
  }
  return esc(m.body);
}
function renderMsg(m){
  const time = m.created_at ? new Date(m.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : '';
  const atts = (m.attachments||[]).map(renderAttachment).join('');
  const reacts = (m.reactions||[]).map(r=>r.emoji).join(' ');
  const mine = m.sender===meId;
  const actions = m.is_deleted ? '' : `<span class="msg-actions">
    <button data-act="react" data-emoji="👍" data-id="${m.id}">👍</button>
    <button data-act="react" data-emoji="❤️" data-id="${m.id}">❤️</button>
    <button data-act="react" data-emoji="😂" data-id="${m.id}">😂</button>
    <button data-act="reply" data-id="${m.id}">↩ Reply</button>
    ${mine?`<button data-act="edit" data-id="${m.id}">✏️ Edit</button><button data-act="delete" data-id="${m.id}">🗑️ Delete</button>`:''}
  </span>`;
  const content = m.kind==='location' && m.latitude!=null ? renderLocation(m) : renderBody(m);
  if(m.is_deleted){
    const label = mine ? 'You unsent a message' : 'This message was unsent';
    return `<div class="msg-row ${mine?'mine':''}"><div class="msg deleted" data-msg="${m.id}">${label}<small>${time}</small></div></div>`;
  }
  const senderAv = mine ? '' : `<span class="avatar-wrap">${avatarHtml(m.sender_username||'', null)}</span>`;
  return `<div class="msg-row ${mine?'mine':''}">${senderAv}<div class="msg ${mine?'mine':''}" data-msg="${m.id}">
    <b>${esc(m.sender_username||'')}</b> ${m.reply_to?`<span class="reply-tag">↩ reply to #${m.reply_to}</span> `:''}${content} ${atts}
    <small>${time} ${m.is_edited?'(edited)':''} <span class="reacts">${reacts}</span></small>${actions}</div></div>`;
}
// --- v6: message list with day dividers + info-panel filters ---
let currentMsgs = [], msgFilter = null;
function msgMatchesFilter(m){
  if(msgFilter === 'voice') return (m.attachments||[]).some(a=>a.is_audio);
  if(msgFilter === 'media') return (m.attachments||[]).length > 0;
  return true;
}
function renderMsgList(msgs){
  let html = '', lastDay = '', firstTimeOfDay = {};
  const sorted = [...msgs];
  for(const m of sorted){
    const d = m.created_at ? new Date(m.created_at) : null;
    const key = d ? d.toDateString() : '';
    if(d && !(key in firstTimeOfDay)) firstTimeOfDay[key] = d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  }
  for(const m of sorted){
    const d = m.created_at ? new Date(m.created_at) : null;
    const key = d ? d.toDateString() : '';
    if(d && key !== lastDay){
      lastDay = key;
      const today = new Date().toDateString();
      const yest = new Date(Date.now()-86400000).toDateString();
      const label = key === today ? 'Today' : key === yest ? 'Yesterday' : d.toLocaleDateString([], {weekday:'short', day:'numeric', month:'short'});
      html += `<div class="day-divider">${label} ${firstTimeOfDay[key]||''}</div>`;
    }
    html += renderMsg(m);
  }
  $('messages').innerHTML = html; scrollDown();
}
let infoMuted = false;
function setOnlineStatusUI(isOnline){
  const label = isOnline ? 'Active now' : 'Offline';
  $('chat-status').textContent = label; $('info-status').textContent = label;
}
function updateInfoPanel(){
  const avEl = $('info-avatar'); if(!avEl) return;
  const voiceCount = currentMsgs.filter(m=>(m.attachments||[]).some(a=>a.is_audio)).length;
  const mediaCount = currentMsgs.filter(m=>(m.attachments||[]).length).length;
  $('info-voice-count').textContent = voiceCount;
  $('info-media-count').textContent = mediaCount;
  if(!currentConvData){
    avEl.innerHTML = avatarWithDot(myUsername, myProfile?.avatar, false, 'avatar-lg');
    $('info-name').textContent = myUsername || 'You';
    $('info-status').textContent = '';
    $('chat-peer-avatar').innerHTML = '';
    $('info-block-wrap').style.display = 'none'; $('info-block-row').style.display = 'none';
    return;
  }
  const others = (currentConvData.memberships||[]).filter(m=>m.user!==meId);
  const myMembership = (currentConvData.memberships||[]).find(m=>m.user===meId);
  infoMuted = !!myMembership?.is_muted;
  $('info-mute-label').textContent = infoMuted ? 'Muted' : 'Mute';
  $('info-mute-btn').style.opacity = infoMuted ? '.55' : '1';
  if(currentConvData.type === 'group'){
    const title = currentConvData.title || 'Group';
    avEl.innerHTML = `<span class="avatar-wrap"><span class="avatar avatar-fallback avatar-lg">👥</span></span>`;
    $('info-name').textContent = title;
    $('info-status').textContent = `${(currentConvData.memberships||[]).length} members`;
    $('chat-status').textContent = `${(currentConvData.memberships||[]).length} members`;
    $('chat-peer-avatar').innerHTML = `<span class="avatar-wrap"><span class="avatar avatar-fallback">👥</span></span>`;
    $('info-block-wrap').style.display = 'none'; $('info-block-row').style.display = 'none';
  } else {
    const other = others[0];
    const name = other?.username || 'Conversation';
    avEl.innerHTML = avatarWithDot(name, other?.avatar, !!other?.is_online, 'avatar-lg');
    $('info-name').textContent = name;
    $('chat-peer-avatar').innerHTML = avatarWithDot(name, other?.avatar, !!other?.is_online);
    setOnlineStatusUI(!!other?.is_online);
    $('info-block-wrap').style.display = ''; $('info-block-row').style.display = '';
  }
}
function setMsgFilter(kind){
  msgFilter = (msgFilter === kind) ? null : kind;
  document.querySelectorAll('.info-row').forEach(r=>r.classList.remove('active'));
  if(msgFilter === 'voice') $('info-voice-row').classList.add('active');
  if(msgFilter === 'media') $('info-media-row').classList.add('active');
  renderMsgList(msgFilter ? currentMsgs.filter(msgMatchesFilter) : currentMsgs);
}
function scrollDown(){ const el=$('messages'); el.scrollTop = el.scrollHeight; }
async function sendPayload(payload){
  // Prefer the WebSocket; if it is not open (still connecting / dropped),
  // fall back to the REST API instead of silently losing the message -
  // REST message creation accepts the same body + attachment_id.
  if(ws && ws.readyState === WebSocket.OPEN){
    ws.send(JSON.stringify({type:'send_message', ...payload}));
    return true;
  }
  if(!currentConv) return false;
  const r = await api('/api/chat/messages/', {method:'POST',
    body: JSON.stringify({conversation: currentConv, body: payload.body || '', reply_to: payload.reply_to || null, attachment_id: payload.attachment_id || undefined,
      ...(payload.location ? {latitude: payload.location.latitude, longitude: payload.location.longitude, live_minutes: payload.location.live_minutes || undefined} : {})})});
  if(r && r.id){ openConv(currentConv); return true; }
  return false;
}
$('send-form').addEventListener('submit', async e=>{
  e.preventDefault(); const body = $('msg-input').value.trim(); if(!body) return;
  if(!currentConv) return alert('Open a conversation first');
  const ok = await sendPayload({body, reply_to: replyToId});
  if(!ok) return alert('Could not send - connection problem. Try again.');
  $('msg-input').value=''; replyToId = null; $('reply-bar').hidden = true;
});
// --- Message actions: react / reply / edit / delete (buttons rendered per message) ---
$('messages').addEventListener('click', async e=>{
  const btn = e.target.closest('button[data-act]'); if(!btn) return;
  const id = +btn.dataset.id, act = btn.dataset.act;
  const msgEl = document.querySelector(`[data-msg="${id}"]`);
  if(act==='react'){
    const r = await api(`/api/chat/messages/${id}/react/`, {method:'POST', body: JSON.stringify({emoji: btn.dataset.emoji})});
    const span = msgEl?.querySelector('.reacts');
    if(span) span.textContent = r.reacted ? (span.textContent + ' ' + btn.dataset.emoji).trim() : span.textContent.replace(btn.dataset.emoji, '').trim();
  }
  if(act==='reply'){ replyToId = id; $('reply-bar').hidden = false; $('msg-input').focus(); }
  if(act==='edit'){
    const current = msgEl?.childNodes[2]?.textContent?.trim() || '';
    const body = prompt('Edit your message:', current); if(body===null || !body.trim()) return;
    const updated = await api(`/api/chat/messages/${id}/`, {method:'PATCH', body: JSON.stringify({body: body.trim()})});
    if(updated.id) openConv(currentConv);
  }
  if(act==='delete'){
    if(!confirm('Delete this message?')) return;
    await api(`/api/chat/messages/${id}/`, {method:'DELETE'});
    openConv(currentConv);
  }
});
$('reply-cancel').onclick = ()=>{ replyToId = null; $('reply-bar').hidden = true; };
// --- Emoji picker: inserts into the message box (and you can also just type/paste emojis) ---
$('emoji-panel').innerHTML = EMOJIS.map(em=>`<span data-emoji="${em}">${em}</span>`).join('');
$('emoji-btn').onclick = ()=>{ $('emoji-panel').hidden = !$('emoji-panel').hidden; };
$('emoji-panel').addEventListener('click', e=>{
  const s = e.target.closest('span[data-emoji]'); if(!s) return;
  $('msg-input').value += s.dataset.emoji; $('msg-input').focus();
});
// --- Clear chat: hides history for you only, the other person keeps theirs ---
$('clear-btn').onclick = async ()=>{
  if(!currentConv) return alert('Open a conversation first');
  if(!confirm('Clear this chat? Messages will be hidden for you only. The other person keeps their copy.')) return;
  await api(`/api/chat/conversations/${currentConv}/clear/`, {method:'POST', body:'{}'});
  $('messages').innerHTML=''; loadConvs();
};
// --- Search messages in the current conversation (Enter to search, clear the box + Enter for all) ---
$('msg-search').addEventListener('keydown', async e=>{
  if(e.key!=='Enter' || !currentConv) return; e.preventDefault();
  const q = e.target.value.trim();
  const data = await api(`/api/chat/messages/?conversation=${currentConv}` + (q ? '&q='+encodeURIComponent(q) : ''));
  const msgs = data.results || data;
  if(msgs.length) renderMsgList(msgs); else $('messages').innerHTML = '<p style="padding:16px">No messages found.</p>';
});
// --- Notifications ---
async function loadNotifCount(){ try{ const d = await api('/api/notifications/unread-count/'); $('notif-count').textContent = d.unread ? `(${d.unread})` : ''; }catch(_){} }
$('notif-btn').onclick = async ()=>{
  const panel = $('notif-panel');
  if(!panel.hidden){ panel.hidden = true; return; }
  const data = await api('/api/notifications/'); const list = data.results || data;
  panel.innerHTML = (list.length ? list.map(n=>`<div>${n.is_read?'':'🔵 '}${esc(n.actor_username||'Someone')}: ${esc(n.text||'New message')} <small>${new Date(n.created_at).toLocaleString()}</small></div>`).join('') : '<div>No notifications</div>')
    + '<button id="notif-read-all">Mark all read</button>';
  panel.hidden = false;
  document.getElementById('notif-read-all').onclick = async ()=>{ await api('/api/notifications/read-all/', {method:'POST', body:'{}'}); panel.hidden=true; loadNotifCount(); };
};
// --- Block the other user in a private chat ---
$('block-btn').onclick = async ()=>{
  if(!otherUserId) return;
  if(!confirm('Block this user? Neither of you will be able to send new messages in this chat, or start new chats.')) return;
  await api('/api/auth/block/', {method:'POST', body: JSON.stringify({user_id: otherUserId})});
  alert('User blocked.'); loadConvs();
};
// --- Profile and Settings are separate pages now (v6): the old
// prompt-chain and the in-panel appearance editor are gone. ---
$('profile-btn').onclick = ()=>{ location.href = '/profile/'; };
$('me-wrap').style.cursor = 'pointer';
$('me-wrap').onclick = ()=>{ location.href = '/profile/'; };
$('appearance-btn').onclick = ()=>{ location.href = '/settings/'; };
$('settings-btn').onclick = ()=>{ location.href = '/settings/'; };

$('msg-input').addEventListener('input', ()=>{
  if(!ws) return; ws.send(JSON.stringify({type:'typing', is_typing:true}));
  clearTimeout(typingTimer); typingTimer=setTimeout(()=>ws?.send(JSON.stringify({type:'typing', is_typing:false})), 1200);
});
$('file-input').addEventListener('change', async e=>{
  const file = e.target.files[0]; e.target.value = '';
  if(!file) return;
  if(!currentConv) return alert('Open a conversation first, then attach the file.');
  // Client-side guardrails (the server enforces the same limits)
  const ALLOWED = ['.jpg','.jpeg','.png','.gif','.webp','.pdf','.doc','.docx','.txt','.zip','.mp3','.wav','.ogg','.webm','.m4a','.aac'];
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
  if(!ALLOWED.includes(ext)) return alert('File type ' + ext + ' is not allowed. Allowed: images, PDF, DOC/DOCX, TXT, ZIP and audio (mp3/wav/ogg/webm/m4a).');
  if(file.size > 10 * 1024 * 1024) return alert('File is too large - the limit is 10 MB.');
  let att;
  try{
    const fd = new FormData(); fd.append('file', file);
    const r = await fetch('/api/chat/attachments/', {method:'POST', headers:{Authorization:'Bearer '+token}, body:fd});
    att = await r.json().catch(()=>({detail: 'Server returned an unreadable response (HTTP ' + r.status + ')'}));
    if(!r.ok || !att.id) return alert('Upload failed: ' + (att.detail || JSON.stringify(att)));
  }catch(_){ return alert('Upload failed: network error. Check your connection and try again.'); }
  // Send the attachment id, not a text message - the server links the uploaded
  // file to the new message and broadcasts it so both sides render a link/preview.
  // sendPayload uses the WebSocket, or REST if the socket is not open.
  const ok = await sendPayload({body:'', attachment_id: att.id});
  if(!ok) alert('The file uploaded but could not be sent - connection problem. Try again.');
});
// --- Location sharing: one-time pin + live location (auto-expires server-side) ---
let liveWatchId = null, liveMsgId = null, liveLastSent = 0, liveLastPos = null;
$('loc-btn').onclick = ()=>{ $('location-panel').hidden = !$('location-panel').hidden; $('emoji-panel').hidden = true; };
function geoError(err){
  alert('Could not get your location: ' + err.message +
    '\nNote: location needs permission, and a secure page (https or localhost).');
}
async function sendLocationUpdate(lat, lng, stop=false){
  if(!liveMsgId) return;
  if(ws && ws.readyState === WebSocket.OPEN)
    ws.send(JSON.stringify({type:'location_update', message_id: liveMsgId, latitude: lat, longitude: lng, stop}));
  else
    await api(`/api/chat/messages/${liveMsgId}/location/`, {method:'POST',
      body: JSON.stringify(stop ? {stop:true} : {latitude: lat, longitude: lng})});
}
function stopLiveLocation(notifyServer=true){
  if(liveWatchId !== null){ navigator.geolocation.clearWatch(liveWatchId); liveWatchId = null; }
  if(liveMsgId && notifyServer) sendLocationUpdate(liveLastPos?.latitude, liveLastPos?.longitude, true);
  liveMsgId = null; $('live-bar').hidden = true;
}
$('live-stop').onclick = ()=>{ stopLiveLocation(true); alert('Live location stopped.'); };
function startLiveWatch(){
  if(!('geolocation' in navigator)) return;
  liveWatchId = navigator.geolocation.watchPosition(pos=>{
    liveLastPos = {latitude: pos.coords.latitude, longitude: pos.coords.longitude};
    const now = Date.now();
    // Throttle: at most one update every 10 seconds
    if(now - liveLastSent < 10000) return;
    liveLastSent = now;
    sendLocationUpdate(liveLastPos.latitude, liveLastPos.longitude);
  }, ()=>{}, {enableHighAccuracy: true, maximumAge: 5000});
  $('live-bar').hidden = false;
}
$('location-panel').addEventListener('click', async e=>{
  const btn = e.target.closest('button[data-loc]'); if(!btn) return;
  $('location-panel').hidden = true;
  if(!currentConv) return alert('Open a conversation first');
  if(!('geolocation' in navigator)) return alert('This browser/device has no location support.');
  const mode = btn.dataset.loc;
  navigator.geolocation.getCurrentPosition(async pos=>{
    const {latitude, longitude} = pos.coords;
    // If the REST fallback is used, the new message comes back in the
    // response; over WS we learn its id from the broadcast instead.
    const before = new Set([...document.querySelectorAll('[data-msg]')].map(el=>el.dataset.msg));
    const ok = await sendPayload({body:'', location:{latitude, longitude, live_minutes: mode==='once' ? null : +mode}});
    if(!ok) return alert('Could not share location - connection problem.');
    if(mode !== 'once'){
      // Find the location message id: prefer the newest location card that is mine
      const waitForId = setInterval(()=>{
        const cards = [...document.querySelectorAll('[data-loc-msg]')];
        const mine = cards.filter(c=>c.closest('.msg')?.classList.contains('mine') && !before.has(c.dataset.locMsg));
        if(mine.length){ liveMsgId = +mine[mine.length-1].dataset.locMsg; clearInterval(waitForId); startLiveWatch(); }
      }, 400);
      setTimeout(()=>clearInterval(waitForId), 6000);
    }
  }, geoError, {enableHighAccuracy: true, timeout: 15000});
});
window.addEventListener('beforeunload', ()=>{ if(liveMsgId) stopLiveLocation(true); });

// --- Voice notes: record with the mic, upload as an audio file, send it ---
let recorder = null, recChunks = [], recStream = null, recTimer = null, recSecs = 0, recCancelled = false;
function fmtTime(s){ return Math.floor(s/60) + ':' + String(s%60).padStart(2,'0'); }
function stopRecTracks(){ recStream?.getTracks().forEach(t=>t.stop()); recStream = null; }
$('rec-cancel').onclick = ()=>{ recCancelled = true; recorder?.stop(); };
$('mic-btn').onclick = async ()=>{
  if(recorder && recorder.state === 'recording'){ recorder.stop(); return; }
  if(!currentConv) return alert('Open a conversation first, then record.');
  if(!navigator.mediaDevices?.getUserMedia) return alert('Voice recording is not supported in this browser (it needs https or localhost).');
  try{ recStream = await navigator.mediaDevices.getUserMedia({audio: true}); }
  catch(_){ return alert('Microphone permission was denied. Allow mic access to send voice notes.'); }
  const mime = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(t=>window.MediaRecorder?.isTypeSupported?.(t)) || '';
  recorder = new MediaRecorder(recStream, mime ? {mimeType: mime} : undefined);
  recChunks = []; recCancelled = false; recSecs = 0;
  $('rec-time').textContent = '0:00'; $('rec-bar').hidden = false; $('mic-btn').classList.add('recording');
  recTimer = setInterval(()=>{ recSecs++; $('rec-time').textContent = fmtTime(recSecs); }, 1000);
  recorder.ondataavailable = e=>{ if(e.data.size) recChunks.push(e.data); };
  recorder.onstop = async ()=>{
    clearInterval(recTimer); stopRecTracks();
    $('rec-bar').hidden = true; $('mic-btn').classList.remove('recording');
    if(recCancelled || !recChunks.length) return;
    const type = recorder.mimeType || mime || 'audio/webm';
    const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm';
    const blob = new Blob(recChunks, {type});
    const file = new File([blob], 'voice-note.' + ext, {type});
    try{
      const fd = new FormData(); fd.append('file', file);
      const r = await fetch('/api/chat/attachments/', {method:'POST', headers:{Authorization:'Bearer '+token}, body:fd});
      const att = await r.json().catch(()=>({}));
      if(!r.ok || !att.id) return alert('Voice note upload failed: ' + (att.detail || r.status));
      const ok = await sendPayload({body:'', attachment_id: att.id});
      if(!ok) alert('Voice note uploaded but could not be sent - connection problem.');
    }catch(_){ alert('Voice note upload failed: network error.'); }
  };
  recorder.start();
};

$('user-search').addEventListener('input', async e=>{
  const q = e.target.value.trim(); if(q.length<2){ $('search-results').innerHTML=''; return; }
  const data = await api('/api/auth/users/search/?q='+encodeURIComponent(q)); const users = data.results||data;
  $('search-results').innerHTML = users.map(u=>`<label style="display:flex;align-items:center;gap:8px;padding:3px 0"><input type="checkbox" class="pick-user" value="${u.id}"> ${avatarHtml(u.username, u.profile?.avatar)} <span>@${esc(u.username)} ${u.profile?.is_online?'🟢':'⚪'}</span> <button data-chat="${u.id}">Chat</button></label>`).join('');
  document.querySelectorAll('[data-chat]').forEach(b=>b.onclick=async()=>{
    const c = await api('/api/chat/conversations/', {method:'POST', body: JSON.stringify({type:'private', member_ids:[+b.dataset.chat]})});
    loadConvs(); openConv(c.id); });
});
$('new-group').addEventListener('click', async ()=>{
  const ids = [...document.querySelectorAll('.pick-user:checked')].map(x=>+x.value);
  const title = $('group-title').value.trim(); if(!title || !ids.length) return alert('Add a group name and check at least one user');
  const c = await api('/api/chat/conversations/', {method:'POST', body: JSON.stringify({type:'group', title, member_ids:ids})});
  loadConvs(); openConv(c.id);
});
$('logout').onclick = ()=>{ localStorage.clear(); location.href='/login/'; };
// --- Mobile: back from a chat to the conversation list ---
$('back-btn').onclick = ()=>{
  document.body.classList.remove('chat-open');
  ws?.close(); ws = null; currentConv = null; loadConvs();
};
// ================= Chat background (applied here, edited in Settings) ==========
// The wallpaper choice lives on the profile (see Settings page); the chat
// screen only applies it to #messages.
const WP_PRESETS = [
  {key:'default', label:'Default', css:''},
  {key:'ocean', label:'Ocean', css:'linear-gradient(160deg,#0ea5e9,#1e3a8a)'},
  {key:'sunset', label:'Sunset', css:'linear-gradient(160deg,#f59e0b,#db2777)'},
  {key:'forest', label:'Forest', css:'linear-gradient(160deg,#16a34a,#134e4a)'},
  {key:'grape', label:'Grape', css:'linear-gradient(160deg,#8b5cf6,#312e81)'},
  {key:'dots', label:'Dots', css:'radial-gradient(circle at 1px 1px, rgba(148,163,184,.35) 1.5px, transparent 0)', size:'22px 22px'},
];
let wpChoice = '';         // "" | "preset:<key>" | "color:<#hex>" | "image"
function initWallpaper(profile){
  wpChoice = profile?.chat_wallpaper || '';
  applyWallpaper();
}
function applyWallpaper(){
  const el = $('messages'); if(!el) return;
  el.style.backgroundImage = ''; el.style.backgroundColor = '';
  if(!wpChoice) return;
  if(wpChoice.startsWith('preset:')){
    const p = WP_PRESETS.find(x=>x.key === wpChoice.slice(7));
    if(p){ el.style.backgroundImage = p.css; el.style.backgroundSize = p.size || 'cover'; }
  } else if(wpChoice.startsWith('color:')){
    el.style.backgroundColor = wpChoice.slice(6);
  } else if(wpChoice === 'image' && myProfile?.wallpaper){
    el.style.backgroundImage = `url("${mediaUrl(myProfile.wallpaper)}")`;
    el.style.backgroundSize = 'cover';
  }
}

// ================= v6 UI wiring: tabs, info panel, mobile nav =================
document.querySelectorAll('.filter-tab').forEach(tab=>tab.onclick = ()=>{
  convFilter = tab.dataset.filter;
  document.querySelectorAll('.filter-tab').forEach(x=>x.classList.toggle('active', x===tab));
  renderConvList();
});
function setMobileNav(name){
  document.querySelectorAll('.mobile-nav-btn').forEach(b=>b.classList.toggle('active', b.dataset.nav===name));
}
document.querySelectorAll('.mobile-nav-btn').forEach(btn=>btn.onclick = ()=>{
  const nav = btn.dataset.nav; setMobileNav(nav);
  document.body.classList.remove('chat-open');
  if(nav === 'groups'){ convFilter = 'groups'; }
  else if(nav === 'chats'){ convFilter = 'all'; }
  if(nav !== 'profile'){
    document.querySelectorAll('.filter-tab').forEach(x=>x.classList.toggle('active', x.dataset.filter===convFilter));
    renderConvList();
  }
  if(nav === 'profile'){ location.href = '/profile/'; }
});
$('sidebar-search-btn').onclick = ()=>{ $('user-search').scrollIntoView({behavior:'smooth'}); $('user-search').focus(); };
$('sidebar-new-btn').onclick = ()=>{ $('group-create').open = true; $('group-title').focus(); };
function toggleMsgSearch(){
  const row = $('msg-search-row'); row.hidden = !row.hidden;
  if(!row.hidden) $('msg-search').focus();
  if(window.innerWidth <= 1250) $('info-panel').classList.remove('open');
}
$('header-search-btn').onclick = toggleMsgSearch;
$('info-btn').onclick = ()=>{ $('info-panel').classList.toggle('open'); updateInfoPanel(); };
$('plus-btn').onclick = ()=>{ $('emoji-panel').hidden = !$('emoji-panel').hidden; $('location-panel').hidden = true; };
$('info-search-btn').onclick = toggleMsgSearch;
$('info-block-btn').onclick = ()=>$('block-btn').click();
$('info-block-row').onclick = ()=>$('block-btn').click();
$('info-clear-row').onclick = ()=>$('clear-btn').click();
$('info-voice-row').onclick = ()=>setMsgFilter('voice');
$('info-media-row').onclick = ()=>setMsgFilter('media');
$('info-mute-btn').onclick = async ()=>{
  if(!currentConv) return alert('Open a conversation first');
  const r = await api(`/api/chat/conversations/${currentConv}/mute/`, {method:'POST', body: JSON.stringify({muted: !infoMuted})});
  if(typeof r.is_muted === 'boolean'){
    infoMuted = r.is_muted;
    const mine = (currentConvData?.memberships||[]).find(m=>m.user===meId);
    if(mine) mine.is_muted = infoMuted;
    const stored = allConvs.find(c=>c.id===currentConv);
    const sm = stored?.memberships?.find(m=>m.user===meId); if(sm) sm.is_muted = infoMuted;
    updateInfoPanel();
  }
};

loadMe().then(()=>{ loadConvs(); loadNotifCount(); });
