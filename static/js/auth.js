const err = t => document.querySelector('.err').textContent = t;
async function post(url, data){ const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); const j = await r.json().catch(()=>({})); if(!r.ok) throw j; return j; }
document.getElementById('login-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ const j = await post('/api/auth/login/', Object.fromEntries(f));
    localStorage.setItem('access', j.access); localStorage.setItem('refresh', j.refresh); location.href='/';
  }catch(j){ err(JSON.stringify(j)); }});
document.getElementById('register-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ await post('/api/auth/register/', Object.fromEntries(f)); location.href='/login/';
  }catch(j){ err(JSON.stringify(j)); }});
