const err = t => document.querySelector('.err').textContent = t;
async function post(url, data){ const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); const j = await r.json().catch(()=>({})); if(!r.ok) throw j; return j; }
document.getElementById('login-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ const j = await post('/api/auth/login/', Object.fromEntries(f));
    localStorage.setItem('access', j.access); localStorage.setItem('refresh', j.refresh); location.href='/';
  }catch(j){
    // Friendly message for the (common) unverified-email case
    if(j.code === 'email_not_verified' || (j.detail || '').includes('not verified'))
      err('Your email is not verified yet. Click the link in your verification email — or use the resend form below.');
    else if((j.detail || '').includes('No active account'))
      err('Username or password is incorrect.');
    else err(j.detail || JSON.stringify(j));
  }});
document.getElementById('register-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ const j = await post('/api/auth/register/', Object.fromEntries(f));
    // Do NOT go straight to the app: the account must be verified first.
    e.target.reset();
    document.querySelector('.msg').textContent =
      (j.detail || 'Account created.') + ' (Local run? The email is printed in the server terminal.)';
  }catch(j){ err(JSON.stringify(j)); }});
document.getElementById('forgot-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ const j = await post('/api/auth/password-reset/', Object.fromEntries(f));
    document.querySelector('#forgot-form .msg').textContent =
      j.detail + ' (Local run? The email is printed in the server terminal.)';
  }catch(j){ document.querySelector('#forgot-form .msg').textContent = 'Something went wrong, try again.'; }});
document.getElementById('resend-form')?.addEventListener('submit', async e=>{
  e.preventDefault(); const f = new FormData(e.target);
  try{ const j = await post('/api/auth/resend-verification/', Object.fromEntries(f));
    document.querySelector('#resend-form .msg').textContent = j.detail;
  }catch(j){ document.querySelector('#resend-form .msg').textContent = 'Something went wrong, try again.'; }});
// --- v6: collapsible forgot-password / resend-verification forms ---
// Both forms exist in the DOM (auth handlers above use them); they are
// hidden until their toggle link is clicked.
[['forgot-toggle','forgot-form'],['resend-toggle','resend-form']].forEach(([toggleId, formId])=>{
  const toggle = document.getElementById(toggleId), form = document.getElementById(formId);
  if(!toggle || !form) return;
  toggle.addEventListener('click', e=>{
    e.preventDefault();
    form.hidden = !form.hidden;
    if(!form.hidden) form.querySelector('input')?.focus();
  });
});
