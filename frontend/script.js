// MediGuard AI - Frontend Script
// Ensures DOM is ready before initializing

(function() {
  'use strict';
  
  // Wait for DOM to be fully loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  
  function init() {
  // configuration: tries meta tag mg-api-base, otherwise fallback to default
  const metaApi = document.querySelector('meta[name="mg-api-base"]');
  const originBase = (window.location && window.location.origin && window.location.origin.startsWith('http'))
    ? window.location.origin
    : "http://127.0.0.1:8000";
  const configuredBase = (metaApi && metaApi.content) ? metaApi.content : originBase;
  const API_BASE = configuredBase.replace(/\/+$/, '');
  // websocket url derived from API_BASE (http -> ws, https -> wss)
  const WS_URL = (API_BASE.startsWith('https') ? 'wss' : 'ws') + '://' + API_BASE.replace(/^https?:\/\//, '') + '/ws';

  // Demo fallback meds (unchanged content structure)
  const MEDS = {
    'BAT12345': { name:'Paracetamol 500mg', batch:'BAT12345', quality:95, risk:'low', supplierId:'PharmaCorp' },
    'BAT67890': { name:'Amoxicillin 250mg', batch:'BAT67890', quality:72, risk:'medium', supplierId:'HealthMeds' },
    'BAT54321': { name:'Aspirin 75mg', batch:'BAT54321', quality:38, risk:'high', supplierId:'MediCare' },
    'BAT99999': { name:'Cipro 500mg', batch:'BAT99999', quality:28, risk:'high', supplierId:'GlobalPharma' }
  };

  // UI refs
  const backendStatus = document.getElementById('backendStatus');
  const splash = document.getElementById('splashView');
  const auth = document.getElementById('authView');
  const portal = document.getElementById('portalView');
  const startBtn = document.getElementById('startBtn');
  const portals = Array.from(document.querySelectorAll('.portal-card'));
  const selectedRoleEl = document.getElementById('selectedRole');
  const authTitle = document.getElementById('authTitle');
  const authSub = document.getElementById('authSub');
  const loginForm = document.getElementById('loginForm');
  const signupForm = document.getElementById('signupForm');
  const showSignupBtn = document.getElementById('showSignup');
  const backToLoginBtn = document.getElementById('backToLogin');
  const backToPortalBtn = document.getElementById('backToPortal');
  const doLoginBtn = document.getElementById('doLogin');
  const doSignupBtn = document.getElementById('doSignup');
  const loginError = document.getElementById('loginError');
  const signupError = document.getElementById('signupError');
  const currentUserDisplay = document.getElementById('currentUserDisplay');
  const currentUserRole = document.getElementById('currentUserRole');
  const dashTitle = document.getElementById('dashTitle');
  const dashSub = document.getElementById('dashSub');
  const logoutBtn = document.getElementById('logoutBtn');
  const refreshBtn = document.getElementById('refreshBtn');
  const highRiskTableBody = document.querySelector('#highRiskTable tbody');
  const lookupInput = document.getElementById('lookupInput');
  const lookupBtn = document.getElementById('lookupBtn');
  const lookupResult = document.getElementById('lookupResult');
  const fakeScanBtn = document.getElementById('fakeScanBtn');
  const profileBox = document.getElementById('profileBox');
  const loginEmail = document.getElementById('loginEmail');
  const loginPassword = document.getElementById('loginPassword');
  const signupName = document.getElementById('signupName');
  const signupEmail = document.getElementById('signupEmail');
  const signupPhone = document.getElementById('signupPhone');
  const signupPassword = document.getElementById('signupPassword');
  const signupRole = document.getElementById('signupRole');

  // state
  let currentUser = null;
  let ws = null;
  let wsBackoff = 1000; // ms
  const WS_BACKOFF_MAX = 30000;
  let streamPrimed = false;

  // localStorage helpers
  function usersKey(){ return 'medverify_users_v1'; }
  function loadUsers(){ try{return JSON.parse(localStorage.getItem(usersKey())||'{}')}catch(e){return{}} }
  function saveUsers(u){ localStorage.setItem(usersKey(),JSON.stringify(u)); }

  // validations
  function validDisplayName(name){
    if(!name) return false;
    if(name.length < 6) return false;
    const digit = /\d/;
    const special = /[!@#\$%\^&\*\(\)_\-\+=\[\]{};:'",.<>\/\\|?`~]/;
    return digit.test(name) && special.test(name);
  }
  function validPassword(p){ if(!p) return false; return p.length >= 7; }
  function validEmail(e){ if(!e) return false; return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e); }

  function escapeHtml(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // small helper: fetch with timeout + safe JSON
  async function fetchWithTimeout(url, opts = {}, timeout = 6000){
    const controller = new AbortController();
    const id = setTimeout(()=>controller.abort(), timeout);
    try {
      const res = await fetch(url, {...opts, signal: controller.signal});
      clearTimeout(id);
      if(!res.ok) throw new Error('HTTP ' + res.status);
      const contentType = res.headers.get('content-type') || '';
      if(contentType.includes('application/json')){
        return await res.json();
      } else {
        return await res.text();
      }
    } catch (err){
      clearTimeout(id);
      throw err;
    }
  }

  // Check backend status (ping /health or root). If backend doesn't provide /health, fallback to /predict
  async function checkBackend(){
    backendStatus.innerText = 'Checking backend...';
    try {
      const url = API_BASE + '/health';
      const j = await fetchWithTimeout(url, { method: 'GET' }, 2500);
      backendStatus.innerText = 'Backend: OK';
      backendStatus.classList.remove('status-off'); backendStatus.classList.add('status-on');
      return true;
    } catch(_) {
      // try predict as fallback
      try {
        const fallback = API_BASE + '/predict';
        await fetchWithTimeout(fallback, { method: 'OPTIONS' }, 2500); // OPTIONS may succeed even if POST isn't allowed
        backendStatus.innerText = 'Backend: reachable';
        backendStatus.classList.remove('status-off'); backendStatus.classList.add('status-on');
        return true;
      } catch(e){
        backendStatus.innerText = 'Backend: unreachable';
        backendStatus.classList.remove('status-on'); backendStatus.classList.add('status-off');
        return false;
      }
    }
  }

  // CALL backend /predict
  async function callPredict(manufacturer, expiry_date, batch){
    try {
      const payload = { manufacturer, expiry_date, batch };
      const resp = await fetchWithTimeout(API_BASE + "/predict", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(payload)
      }, 5000);
      return resp;
    } catch(err){
      console.warn("Predict error:", err);
      return null;
    }
  }

  // Robust websocket with backoff
  function connectWS() {
    if (ws) try { ws.close(); } catch(e){}
    try {
      ws = new WebSocket(WS_URL);
    } catch (e) {
      console.warn("WS new error", e);
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.info("WS connected to", WS_URL);
      wsBackoff = 1000;
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if(data.event === "alert" && data.alert){
          const a = data.alert;
          // show non-blocking notification instead of alert()
          showNotification(`ALERT (${a.level}): ${a.message}`, a.level);
          renderHighRiskTable();
        } else if(data.event === "test_result" && data.payload){
          console.log("test_result:", data.payload);
        }
      } catch(e){}
    };

    ws.onclose = () => {
      console.info("WS closed, reconnecting...");
      scheduleReconnect();
    };
    ws.onerror = (e) => {
      console.warn("WS error", e);
      ws.close();
    };
  }

  function scheduleReconnect(){
    setTimeout(()=>{
      wsBackoff = Math.min(wsBackoff * 1.8, WS_BACKOFF_MAX);
      console.info("Attempting WS reconnect, backoff=", wsBackoff);
      connectWS();
    }, wsBackoff);
  }

  // UI rendering
  function renderProfile(){
    if(!currentUser) return;
    profileBox.innerHTML = `
      <div><strong>${escapeHtml(currentUser.name||'')}</strong></div>
      <div class="small muted">${escapeHtml(currentUser.email||'')}</div>
      <div class="small muted">Role: ${escapeHtml(currentUser.role||'')}</div>
      <div class="small muted">Phone: ${escapeHtml(currentUser.phone||'')}</div>
    `;
  }

  // Try to fetch high-risk list from backend (/highrisk expected). If not present, use local MEDS.
  async function renderHighRiskTable(){
    highRiskTableBody.innerHTML = '';
    let list = null;
    try {
      const resp = await fetchWithTimeout(API_BASE + '/highrisk?limit=25', { method: 'GET' }, 4000);
      if (Array.isArray(resp)) {
        list = resp;
      }
    } catch(e){
      console.warn('Failed to load high risk list from backend', e);
    }
    if(list === null){
      // fallback to local demo data when backend has no records yet
      list = Object.values(MEDS).filter(m => m.risk === 'high' || m.quality < 50);
    }

    const users = loadUsers();
    const suppliers = {};
    Object.values(users).forEach(u=>{
      if(u.role === 'pharmacy'){
        suppliers[u.name] = u.phone || '';
      }
    });

    list.forEach(m=>{
      const name = m.name || m.med || m.product || 'Unknown';
      const batch = m.batch || m.batch_no || m.id || '--';
      const quality = (m.quality !== undefined) ? (String(m.quality).endsWith('%') ? m.quality : (m.quality + '%')) : '--';
      const risk = (m.risk || (m.quality && parseInt(m.quality) < 50 ? 'high' : 'low')).toUpperCase();
      const supplier = m.supplier || m.supplierId || 'Unknown';
      const tr = document.createElement('tr');
      const phoneLine = m.manufacturer_phone ? `<div class="small muted">${escapeHtml(m.manufacturer_phone)}</div>` : '';
      tr.innerHTML = `
        <td>${escapeHtml(name)}</td>
        <td>${escapeHtml(batch)}</td>
        <td>${escapeHtml(quality)}</td>
        <td><span class="chip ${risk.toLowerCase().includes('high') ? 'fail' : 'pass'}">${risk}</span></td>
        <td>
          <div>${escapeHtml(supplier)}</div>
          ${phoneLine}
        </td>
      `;
      highRiskTableBody.appendChild(tr);
    });

    if (!list.length) {
      highRiskTableBody.innerHTML = `<tr><td colspan="5"><div class="small muted">No alerts yet. Run a lookup or start the simulator.</div></td></tr>`;
    }
  }

  // Lookup: try local first, then backend; if backend returns fake_score, show it and manufacturer phone if present.
  async function doLookup(batch){
    lookupResult.innerHTML='';
    const key = (batch||'').trim().toUpperCase();
    if(!key){
      lookupResult.innerHTML = '<div class="small muted">Enter a batch number</div>';
      return;
    }

    const m = MEDS[key];
    if(!m){
      // not in local MEDS: try backend simulation
      const backend = await callPredict("Unknown", null, key);
      if(backend){
        showLookupResultFromBackend(key, backend);
      } else {
        lookupResult.innerHTML = `<div class="small muted">No data found for <strong>${escapeHtml(key)}</strong></div>`;
      }
      return;
    }

    const expiry = m.expiry || null;
    const backendResult = await callPredict(m.supplierId || m.supplier || "Unknown", expiry, key);

    // compute display quality: prefer backend's fake_score if present
    let qualityDisplay = m.quality;
    if(backendResult && backendResult.fake_score !== undefined){
      qualityDisplay = Math.round((1 - (backendResult.fake_score || 0)) * 100);
    }

    // try to merge phone from saved users or backend
    let supplierPhone = '';
    const users = loadUsers();
    Object.values(users).forEach(u=>{
      if(u.name === m.supplierId) supplierPhone = u.phone || supplierPhone;
    });
    if(backendResult && backendResult.manufacturer_phone){
      supplierPhone = supplierPhone || backendResult.manufacturer_phone;
    }

    lookupResult.innerHTML = `
      <div style="padding:12px;border-radius:8px;background:#fafbff;border:1px solid #eef6ff">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:700">${escapeHtml(m.name)}</div>
            <div class="small muted">Batch ${escapeHtml(m.batch)}</div>
          </div>
          <div style="text-align:right">
            <div style="font-weight:700">${qualityDisplay}%</div>
            <div class="small muted">${(m.risk||'').toUpperCase()}</div>
          </div>
        </div>
        <div style="margin-top:8px" class="small muted">
          Supplier: ${escapeHtml(m.supplierId)}
          ${ supplierPhone ? `<div>Phone: ${escapeHtml(supplierPhone)}</div>` : '' }
          ${ backendResult ? `<div style="margin-top:6px">ML: score=${backendResult.fake_score}, predicted_fake=${backendResult.predicted_fake}</div>` : '' }
        </div>
      </div>
    `;
  }

  function showLookupResultFromBackend(batch, backend) {
    const title = backend.product_name || backend.med || ('Batch ' + batch);
    const quality = backend.fake_score !== undefined ? Math.round((1 - backend.fake_score) * 100) : (backend.quality || '—');
    const supplier = backend.manufacturer || backend.supplier || 'Unknown';
    const phone = backend.manufacturer_phone || backend.phone || '';
    lookupResult.innerHTML = `
      <div style="padding:12px;border-radius:8px;background:#fffdfa;border:1px solid #fff0f0">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <div style="font-weight:700">${escapeHtml(title)}</div>
            <div class="small muted">Batch ${escapeHtml(batch)}</div>
          </div>
          <div style="text-align:right">
            <div style="font-weight:700">${escapeHtml(String(quality))}%</div>
            <div class="small muted">${backend.predicted_fake ? 'SUSPECT' : 'OK'}</div>
          </div>
        </div>
        <div style="margin-top:8px" class="small muted">
          Supplier: ${escapeHtml(supplier)}
          ${ phone ? `<div>Phone: ${escapeHtml(phone)}</div>` : '' }
          <div style="margin-top:6px">Raw backend response: <pre style="white-space:pre-wrap">${escapeHtml(JSON.stringify(backend, null, 2))}</pre></div>
        </div>
      </div>
    `;
  }

  // Event wiring - with error handling
  if(startBtn) startBtn.addEventListener('click', ()=>{ window.scrollTo({top:0,behavior:'smooth'}); });
  portals.forEach(p=>{ 
    if(p) {
      p.style.cursor = 'pointer';
      p.addEventListener('click', ()=> {
        const role = p.getAttribute('data-role');
        if(role) openAuthFor(role);
      });
    }
  });
  backToPortalBtn.addEventListener('click', ()=>{ auth.classList.add('hidden'); splash.classList.remove('hidden'); portal.classList.add('hidden'); });
  showSignupBtn.addEventListener('click', ()=>{ loginForm.classList.add('hidden'); signupForm.classList.remove('hidden'); authTitle.innerText='Create account'; authSub.innerText='Sign up to access the portal'; });
  backToLoginBtn.addEventListener('click', ()=>{ loginForm.classList.remove('hidden'); signupForm.classList.add('hidden'); authTitle.innerText='Sign in'; authSub.innerText='Sign in to access the portal'; });
  doSignupBtn.addEventListener('click', ()=>{
    signupError.style.display='none';
    const name = signupName.value.trim();
    const email = (signupEmail.value||'').trim().toLowerCase();
    const phone = signupPhone.value.trim();
    const pwd = signupPassword.value;
    const role = signupRole.value;
    if(!validDisplayName(name)){ signupError.innerText = 'Display name must be at least 6 chars and include a digit and a special character.'; signupError.style.display='block'; return; }
    if(!validEmail(email)){ signupError.innerText = 'Enter a valid email.'; signupError.style.display='block'; return; }
    if(!validPassword(pwd)){ signupError.innerText = 'Password must be at least 7 characters.'; signupError.style.display='block'; return; }
    const users = loadUsers();
    users[email] = { email, name, phone, role, pwd };
    saveUsers(users);
    currentUser = { email, name, phone, role };
    openPortalFor(currentUser);
  });

  doLoginBtn.addEventListener('click', ()=>{
    loginError.style.display='none';
    const email = (loginEmail.value||'').trim().toLowerCase();
    const pwd = loginPassword.value;
    const users = loadUsers();
    if(!users[email] || users[email].pwd !== pwd){
      loginError.innerText = 'Invalid credentials'; loginError.style.display = 'block'; return;
    }
    const u = users[email];
    currentUser = { email: u.email, name: u.name, phone: u.phone, role: u.role };
    openPortalFor(currentUser);
  });

  if(logoutBtn) logoutBtn.addEventListener('click', ()=>{
    currentUser = null;
    if(splash) splash.classList.remove('hidden');
    if(auth) auth.classList.add('hidden');
    if(portal) portal.classList.add('hidden');
    window.scrollTo({top:0, behavior:'smooth'});
  });

  refreshBtn.addEventListener('click', ()=>{ renderHighRiskTable(); });

  lookupBtn.addEventListener('click', ()=> doLookup(lookupInput.value));
  lookupInput.addEventListener('keydown', (e)=>{ if(e.key === 'Enter') doLookup(lookupInput.value); });

  fakeScanBtn.addEventListener('click', ()=>{
    const keys = Object.keys(MEDS);
    const key = keys[Math.floor(Math.random()*keys.length)];
    lookupInput.value = key;
    doLookup(key);
  });

  function openAuthFor(role){
    if(!role) return;
    try {
      if(splash) splash.classList.add('hidden');
      if(auth) {
        auth.classList.remove('hidden');
        auth.style.display = 'block';
      }
      if(portal) portal.classList.add('hidden');
      if(selectedRoleEl) selectedRoleEl.innerText = role.charAt(0).toUpperCase()+role.slice(1);
      if(loginForm) loginForm.classList.remove('hidden');
      if(signupForm) signupForm.classList.add('hidden');
      if(authTitle) authTitle.innerText = 'Sign in';
      if(authSub) authSub.innerText = 'Sign in to access your '+role+' portal';
      if(loginError) loginError.style.display='none';
      if(signupError) signupError.style.display='none';
      if(loginEmail) loginEmail.value='';
      if(loginPassword) loginPassword.value='';
      window.scrollTo({top:0, behavior:'smooth'});
    } catch(e) {
      console.error('Error in openAuthFor:', e);
    }
  }

  function openPortalFor(user){
    if(!user) return;
    try {
      currentUser = user;
      if(auth) auth.classList.add('hidden');
      if(portal) {
        portal.classList.remove('hidden');
        portal.style.display = 'block';
      }
      if(splash) splash.classList.add('hidden');
      if(currentUserDisplay) currentUserDisplay.innerText = user.name || user.email;
      if(currentUserRole) currentUserRole.innerText = user.role;
      if(dashTitle) dashTitle.innerText = (user.role.charAt(0).toUpperCase()+user.role.slice(1))+' Dashboard';
      if(dashSub) dashSub.innerText = 'Welcome — use the tools below';
      renderHighRiskTable(); 
      renderProfile();
      window.scrollTo({top:0, behavior:'smooth'});
    } catch(e) {
      console.error('Error in openPortalFor:', e);
    }
  }

  // Non-blocking notification system
  function showNotification(message, level = 'INFO') {
    // Remove existing notifications
    const existing = document.getElementById('alertNotification');
    if(existing) existing.remove();
    
    const notification = document.createElement('div');
    notification.id = 'alertNotification';
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      background: ${level === 'CRITICAL' ? '#ef4444' : level === 'WARNING' ? '#f59e0b' : '#3b82f6'};
      color: white;
      padding: 16px 20px;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 10000;
      max-width: 400px;
      font-size: 14px;
      animation: slideIn 0.3s ease;
    `;
    notification.innerHTML = `
      <div style="font-weight:600;margin-bottom:4px">${level}</div>
      <div>${escapeHtml(message)}</div>
      <button onclick="this.parentElement.remove()" style="
        position:absolute;top:8px;right:8px;background:rgba(255,255,255,0.2);
        border:none;color:white;cursor:pointer;padding:4px 8px;border-radius:4px;
        font-size:12px;
      ">✕</button>
    `;
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
      if(notification.parentElement) {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
      }
    }, 5000);
  }

  // INITIAL
  async function primeStream(){
    if(streamPrimed) return;
    try{
      // Reduced frequency: 30 seconds, 3 second intervals (fewer alerts)
      await fetchWithTimeout(API_BASE + '/start_stream', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ seconds: 30, interval: 3 })
      }, 4000);
      streamPrimed = true;
    }catch(err){
      console.warn('Unable to start simulator stream', err);
    }
  }

  // Initialize on page load
  (async function initialize(){
    try {
      const ok = await checkBackend();
      if(ok){
        connectWS();
        primeStream();
      }
      renderHighRiskTable();
    } catch(err) {
      console.error('Initialization error:', err);
    }
  })();

  } // end init function
})(); // end IIFE
