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

async function loadMe(){ const me = await api('/api/auth/me/'); meId = me.id; $('me').textContent = '@'+me.username; }
async function loadConvs(){
  const data = await api('/api/chat/conversations/'); const list = data.results || data;
  $('conversations').innerHTML = list.map(c=>{
    const name = c.title || (c.memberships.find(m=>m.user!==meId)?.username || 'Chat');
    return `<div class="conv ${c.id===currentConv?'active':''}" data-id="${c.id}">
      <strong>${esc(name)}</strong> ${c.unread_count?`<span class="badge">${c.unread_count}</span>`:''}
      <br><small>${esc(c.last_message?.body || (c.last_message?.attachments?.length ? '📎 ' + (c.last_message.attachments[0].original_name || 'Attachment') : 'No messages yet'))}</small></div>`;}).join('');
  document.querySelectorAll('.conv').forEach(el=>el.onclick=()=>openConv(+el.dataset.id));
}
async function openConv(id){
  currentConv = id; ws?.close(); replyToId = null; $('reply-bar').hidden = true;
  currentConvData = await api(`/api/chat/conversations/${id}/`);
  const others = (currentConvData.memberships||[]).filter(m=>m.user!==meId);
  otherUserId = currentConvData.type==='private' && others.length ? others[0].user : null;
  $('chat-header').textContent = currentConvData.title || (others[0]?.username ? '@'+others[0].username : 'Conversation');
  $('block-btn').style.display = otherUserId ? '' : 'none';
  const data = await api(`/api/chat/messages/?conversation=${id}`);
  const msgs = data.results || data;
  $('messages').innerHTML = msgs.map(renderMsg).join(''); scrollDown();
  await api('/api/chat/messages/mark_conversation_read/', {method:'POST', body: JSON.stringify({conversation:id})});
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/chat/${id}/?token=${token}`);
  ws.onmessage = e=>{
    const d = JSON.parse(e.data);
    if(d.type==='chat_message'){ $('messages').insertAdjacentHTML('beforeend', renderMsg({id:d.message_id, sender:d.sender_id, sender_username:d.sender_username, body:d.body, attachments:d.attachments||[], created_at:d.created_at})); scrollDown(); }
    if(d.type==='typing'){ $('typing').textContent = d.is_typing ? `${d.username} is typing…` : ''; }
    if(d.type==='presence'){ $('typing').textContent = `${d.username} is ${d.is_online?'online 🟢':'offline ⚪'}`; }
    if(d.type==='read_receipt'){ document.querySelector(`[data-msg="${d.message_id}"] small`)?.append(' ✓✓'); }
  };
  loadConvs();
}
function renderAttachment(a){
  const name = a.original_name || (a.file||'').split('/').pop() || 'file';
  return a.is_image
    ? `<a href="${a.file}" target="_blank"><img src="${a.file}" alt="${esc(name)}"></a>`
    : `<a href="${a.file}" target="_blank" download>📄 ${esc(name)}</a>`;
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
  return `<div class="msg ${mine?'mine':''}" data-msg="${m.id}">
    <b>${esc(m.sender_username||'')}</b> ${m.reply_to?`<span class="reply-tag">↩ reply to #${m.reply_to}</span> `:''}${m.is_deleted?'<i>message deleted</i>':renderBody(m)} ${atts}
    <small>${time} ${m.is_edited?'(edited)':''} <span class="reacts">${reacts}</span></small>${actions}</div>`;
}
function scrollDown(){ const el=$('messages'); el.scrollTop = el.scrollHeight; }
$('send-form').addEventListener('submit', e=>{
  e.preventDefault(); const body = $('msg-input').value.trim(); if(!body || !ws) return;
  ws.send(JSON.stringify({type:'send_message', body, reply_to: replyToId}));
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
  $('messages').innerHTML = msgs.map(renderMsg).join('') || '<p style="padding:16px">No messages found.</p>'; scrollDown();
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
  if(!confirm('Block this user? You will no longer be able to start new chats with them.')) return;
  await api('/api/auth/block/', {method:'POST', body: JSON.stringify({user_id: otherUserId})});
  alert('User blocked.'); loadConvs();
};
// --- Edit your profile (display name + bio) ---
$('profile-btn').onclick = async ()=>{
  const me = await api('/api/auth/me/');
  const display_name = prompt('Display name:', me.profile?.display_name || me.username); if(display_name===null) return;
  const bio = prompt('Bio:', me.profile?.bio || ''); if(bio===null) return;
  const fd = new FormData(); fd.append('display_name', display_name); fd.append('bio', bio);
  await fetch('/api/auth/profile/', {method:'PATCH', headers:{Authorization:'Bearer '+token}, body: fd});
  alert('Profile updated');
};
$('msg-input').addEventListener('input', ()=>{
  if(!ws) return; ws.send(JSON.stringify({type:'typing', is_typing:true}));
  clearTimeout(typingTimer); typingTimer=setTimeout(()=>ws?.send(JSON.stringify({type:'typing', is_typing:false})), 1200);
});
$('file-input').addEventListener('change', async e=>{
  const file = e.target.files[0]; if(!file || !ws) return;
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch('/api/chat/attachments/', {method:'POST', headers:{Authorization:'Bearer '+token}, body:fd});
  const att = await r.json();
  if(!r.ok || !att.id){ alert('Upload failed: ' + (att.detail || JSON.stringify(att))); return; }
  // Send the attachment id, not a text message - the server links the uploaded
  // file to the new message and broadcasts it so both sides render a link/preview.
  ws.send(JSON.stringify({type:'send_message', body:'', attachment_id: att.id}));
  e.target.value = '';
});
$('user-search').addEventListener('input', async e=>{
  const q = e.target.value.trim(); if(q.length<2){ $('search-results').innerHTML=''; return; }
  const data = await api('/api/auth/users/search/?q='+encodeURIComponent(q)); const users = data.results||data;
  $('search-results').innerHTML = users.map(u=>`<label><input type="checkbox" class="pick-user" value="${u.id}"> @${esc(u.username)} ${u.profile?.is_online?'🟢':'⚪'}</label> <button data-chat="${u.id}">Chat</button><br>`).join('');
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
loadMe().then(()=>{ loadConvs(); loadNotifCount(); });
