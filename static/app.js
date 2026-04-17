
let state = { currentPage:'inventory', me:'', customers:[], warehouseSlots:[], shipping:[], settings:[], activeCustomer:null, activeSlot:null, ocrCache:{inventory:{},orders:{},master:{},ship:{}} };
const $ = id => document.getElementById(id);
function escapeHtml(str){ return (str||'').replace(/[&<>"']/g, s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
function showModal(id){ $(id).classList.remove('hidden'); }
function hideModal(id){ $(id).classList.add('hidden'); }
function setPage(page){
  state.currentPage = page;
  document.querySelectorAll('.page').forEach(el => el.classList.remove('active'));
  $(`page-${page}`).classList.add('active');
  document.querySelectorAll('.nav-card').forEach(btn => btn.classList.toggle('active', btn.dataset.page === page));
  $('currentPage').value = page;
}
function parseItemsFromText(text){
  const lines=(text||'').split('\n').map(s=>s.trim()).filter(Boolean);
  const items=[];
  for(const line of lines){
    let m = line.match(/^(.+?)[=:](\d+)$/);
    if(!m) m = line.match(/^(.+?)x(\d+)$/i);
    if(!m) m = line.match(/^(.+?)\s+(\d+)$/);
    if(m) items.push({product:m[1].trim(), quantity:parseInt(m[2],10)||1});
    else items.push({product:line, quantity:1});
  }
  return items;
}
async function api(url, options={}){
  const res = await fetch(url, { credentials:'same-origin', ...options, headers:{ 'Content-Type':'application/json', ...(options.headers||{}) } });
  let data = {};
  try{ data = await res.json(); }catch{}
  if(!res.ok && !data.error) data.error = `HTTP ${res.status}`;
  return data;
}
function renderCurrentUser(){ $('userPill').textContent = state.me || localStorage.getItem('username') || ''; }
function fillMode(page, data){
  const confId=`${page}Confidence`, warnId=`${page}Warn`, textId=`${page}Text`, resultId=`${page}Result`;
  $(confId).textContent = `信心值：${data.confidence || 0}%`;
  $(warnId).textContent = data.warning || (data.confidence < 80 ? '請確認辨識內容' : '正常');
  $(textId).value = data.text || '';
  state.ocrCache[page] = { original:data.text||'', items:data.items||[], confidence:data.confidence||0 };
  $(resultId).innerHTML = `<div>OCR 完成：${(data.items||[]).length} 筆</div><div class="muted">${new Date().toLocaleString()}</div>`;
}
async function uploadOCR(page, file){
  const fd = new FormData(); fd.append('file', file);
  try{
    const res = await fetch('/api/upload_ocr', { method:'POST', body:fd, credentials:'same-origin' });
    const data = await res.json();
    if(!data.success){ $(page+'Warn').textContent = data.error || 'OCR失敗'; $(page+'Result').innerHTML = `<div class="error">${escapeHtml(data.error||'OCR失敗')}</div>`; return; }
    fillMode(page, data);
  }catch(e){ $(page+'Warn').textContent = '網路錯誤'; $(page+'Result').innerHTML = `<div class="error">網路錯誤</div>`; }
}
async function submitPage(page){
  const customer = $(page+'Customer') ? $(page+'Customer').value.trim() : '';
  const text = $(page+'Text').value.trim();
  const items = parseItemsFromText(text);
  const original = state.ocrCache[page]?.original || text;
  const resultBox = $(page+'Result');
  try{
    if(original && original !== text){
      await api('/api/save_correction', { method:'POST', body: JSON.stringify({ wrong_text: original, correct_text: text }) });
    }
    if(page === 'inventory'){
      const location = $('inventoryLocation').value.trim();
      const data = await api('/api/inventory', { method:'POST', body: JSON.stringify({ customer, location, items }) });
      if(!data.success) throw new Error(data.error || '建立失敗');
      resultBox.innerHTML = `<div>已建立庫存：${items.length} 筆</div>`;
      await refreshInventoryList();
      return;
    }
    if(page === 'orders'){
      const data = await api('/api/order', { method:'POST', body: JSON.stringify({ customer, items }) });
      if(!data.success) throw new Error(data.error || '建立失敗');
      resultBox.innerHTML = `<div>已建立訂單</div><div>客戶：${escapeHtml(customer)}</div><div>狀態：pending</div><div>扣除結果：訂單建立，不扣庫存（待出貨）</div>`;
      await refreshCustomersPanels();
      return;
    }
    if(page === 'master'){
      const data = await api('/api/master_order', { method:'POST', body: JSON.stringify({ customer, items }) });
      if(!data.success) throw new Error(data.error || '建立失敗');
      resultBox.innerHTML = `<div>已更新總單</div><div>客戶：${escapeHtml(customer)}</div><div>同客戶資料已合併、數量已累加</div>`;
      return;
    }
    if(page === 'ship'){
      if(!confirm(`確認要出貨嗎？\n客戶：${customer}\n品項：${items.length} 筆`)) return;
      const data = await api('/api/ship', { method:'POST', body: JSON.stringify({ customer, items }) });
      if(!data.success) throw new Error(data.error || '出貨失敗');
      resultBox.innerHTML = `<div>已出貨成功</div>${(data.breakdown||[]).map(x=>`<div class="result-item"><strong>${escapeHtml(x.customer)}</strong> / ${escapeHtml(x.product)} × ${x.qty}<div>先扣總單：${x.deducted_master}，再扣訂單：${x.deducted_order}，最後扣庫存：${x.deducted_inventory}</div><div>庫存位置：${(x.inventory_locations||[]).map(i=>`${escapeHtml(i.location)}(${i.quantity})`).join(' / ')}</div></div>`).join('')}`;
      await refreshShipping(); await refreshWarehouse(); await refreshCustomersPanels();
      return;
    }
  }catch(e){ resultBox.innerHTML = `<div class="error">${escapeHtml(e.message || '操作失敗')}</div>`; }
}
async function refreshCustomersPanels(){
  const data = await api('/api/customers');
  if(!data.success) return;
  state.customers = data.customers || [];
  renderCustomers();
}
function renderCustomers(){
  const regions = ['北區','中區','南區'];
  const containers = [$('customerPanels'), $('customerPanelsFull')].filter(Boolean);
  containers.forEach(container=>{
    container.innerHTML='';
    regions.forEach(region=>{
      const list = state.customers.filter(c => (c.region || '北區') === region).sort((a,b)=>(a.sort_order||0)-(b.sort_order||0) || a.name.localeCompare(b.name,'zh-Hant'));
      const card = document.createElement('div');
      card.className='region-card';
      card.innerHTML = `<div class="region-title">${region}<span class="muted">拖曳可換區</span></div><div class="customer-chips" data-region="${region}"></div>`;
      const chips = card.querySelector('.customer-chips');
      list.forEach(customer=>{
        const chip = document.createElement('div');
        chip.className='customer-chip';
        chip.textContent=customer.name;
        chip.draggable=true;
        chip.addEventListener('dragstart', e=>e.dataTransfer.setData('text/plain', customer.name));
        chip.addEventListener('click', ()=>openCustomerModal(customer.name));
        chips.appendChild(chip);
      });
      chips.addEventListener('dragover', e=>e.preventDefault());
      chips.addEventListener('drop', async e=>{
        e.preventDefault();
        const name=e.dataTransfer.getData('text/plain');
        const customer=state.customers.find(x=>x.name===name);
        if(!customer) return;
        customer.region=region;
        await api('/api/customers', { method:'POST', body: JSON.stringify(customer) });
        await refreshCustomersPanels();
      });
      container.appendChild(card);
    });
  });
}
async function openCustomerModal(name){
  const data = await api(`/api/customers/${encodeURIComponent(name)}`);
  if(!data.success || !data.customer) return;
  const c = data.customer;
  state.activeCustomer = c;
  $('customerModalTitle').textContent = `編輯客戶：${c.name}`;
  $('customerName').value = c.name || '';
  $('customerPhone').value = c.phone || '';
  $('customerAddress').value = c.address || '';
  $('customerNotes').value = c.notes || '';
  $('customerRegion').value = c.region || '北區';
  $('customerSort').value = c.sort_order || 0;
  const products = state.shipping.filter(r => r.customer === c.name).map(r => `${r.product} × ${r.qty}`);
  $('customerProducts').innerHTML = products.length ? products.map(t => `<div>${escapeHtml(t)}</div>`).join('') : '目前沒有出貨紀錄可顯示。';
  showModal('customerModal');
}
async function saveCustomer(){
  const payload = { name:$('customerName').value.trim(), phone:$('customerPhone').value.trim(), address:$('customerAddress').value.trim(), notes:$('customerNotes').value.trim(), region:$('customerRegion').value, sort_order:parseInt($('customerSort').value||'0',10) };
  const data = await api('/api/customers', { method:'POST', body: JSON.stringify(payload) });
  if(data.success){ hideModal('customerModal'); await refreshCustomersPanels(); } else alert(data.error || '儲存失敗');
}
function renderShipping(){
  const tbody = $('shippingTable');
  tbody.innerHTML = (state.shipping||[]).map(r => `<tr><td>${escapeHtml(r.customer||'')}</td><td>${escapeHtml(r.product||'')}</td><td>${r.qty||''}</td><td>${escapeHtml(r.operator||'')}</td><td>${escapeHtml(r.shipped_at||'')}</td><td>${escapeHtml(r.note||r.source_type||'')}</td></tr>`).join('');
}
async function refreshShipping(){ const data = await api('/api/shipping_records'); if(data.success){ state.shipping = data.records || []; renderShipping(); } }
function renderWarehouse(){
  const wrap = $('warehouseLayout');
  const slots = state.warehouseSlots.length ? state.warehouseSlots : [
    {slot_name:'A後排01', customer:'', product:'', quantity:0, note:''},
    {slot_name:'A後排02', customer:'', product:'', quantity:0, note:''},
    {slot_name:'B後排01', customer:'', product:'', quantity:0, note:''},
    {slot_name:'B後排02', customer:'', product:'', quantity:0, note:''},
    {slot_name:'C前排01', customer:'', product:'', quantity:0, note:''},
  ];
  wrap.innerHTML='';
  slots.forEach(slot=>{
    const el = document.createElement('div');
    el.className='warehouse-box';
    el.innerHTML = `<div class="warehouse-head"><strong>${escapeHtml(slot.slot_name)}</strong><div><button class="small-btn">編輯</button><button class="small-btn">刪除</button></div></div><div class="warehouse-snap">${escapeHtml(slot.customer || '未指定')}<br>${escapeHtml(slot.product || '無商品')}<br>庫存：${slot.quantity || 0}</div><div class="warehouse-meta">${escapeHtml(slot.note || '')}</div>`;
    const [editBtn, delBtn] = el.querySelectorAll('button');
    editBtn.addEventListener('click', () => openSlotModal(slot));
    delBtn.addEventListener('click', async ()=>{ if(!confirm(`刪除格位 ${slot.slot_name}？`)) return; await fetch(`/api/warehouse_slots/${encodeURIComponent(slot.slot_name)}`, { method:'DELETE', credentials:'same-origin' }); await refreshWarehouse(); });
    el.querySelector('.warehouse-snap').addEventListener('click', ()=>openSlotModal(slot));
    wrap.appendChild(el);
  });
}
async function refreshWarehouse(){ const data = await api('/api/warehouse_slots'); if(data.success){ state.warehouseSlots = data.slots || []; renderWarehouse(); } }
function openSlotModal(slot){ state.activeSlot=slot; $('slotName').value=slot.slot_name || ''; $('slotCustomer').value=slot.customer || ''; $('slotProduct').value=slot.product || ''; $('slotQty').value=slot.quantity || 0; $('slotNote').value=slot.note || ''; showModal('warehouseModal'); }
async function saveSlot(){ const payload={ slot_name:$('slotName').value.trim(), customer:$('slotCustomer').value.trim(), product:$('slotProduct').value.trim(), quantity:parseInt($('slotQty').value||'0',10), note:$('slotNote').value.trim() }; const data = await api('/api/warehouse_slots', { method:'POST', body: JSON.stringify(payload) }); if(data.success){ hideModal('warehouseModal'); await refreshWarehouse(); } else alert(data.error || '儲存失敗'); }
async function refreshInventoryList(){ const data = await api('/api/warehouse_slots'); const list = $('inventoryList'); if(data.success){ const rows=(data.slots||[]).map(s=>`<div>${escapeHtml(s.slot_name)}｜${escapeHtml(s.customer||'')}｜${escapeHtml(s.product||'')}｜${s.quantity||0}</div>`); list.innerHTML = rows.join('') || '尚無資料'; } }
async function refreshSettings(){ const data = await api('/api/settings'); if(data.success){ state.settings = data.settings || []; const grid=$('settingsGrid'); grid.innerHTML = state.settings.length ? state.settings.map(s=>`<div><strong>${escapeHtml(s.key)}</strong><div>${escapeHtml(s.value || '')}</div></div>`).join('') : '尚無設定'; } }
function bindFile(id,page){ $(id).addEventListener('change', e => { const file = e.target.files && e.target.files[0]; if(file) uploadOCR(page,file); }); }
function bindNav(){ document.querySelectorAll('.nav-card').forEach(btn => btn.addEventListener('click', () => { setPage(btn.dataset.page); if(btn.dataset.page === 'shipping') refreshShipping(); if(btn.dataset.page === 'warehouse') refreshWarehouse(); if(btn.dataset.page === 'customers') refreshCustomersPanels(); if(btn.dataset.page === 'inventory') refreshInventoryList(); })); }
async function autoLogin(){ const storedUser = localStorage.getItem('username'); const storedPass = localStorage.getItem('password'); if(!storedUser || !storedPass) return false; const res = await fetch('/api/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username:storedUser, password:storedPass }) }); const data = await res.json(); if(data.success){ state.me = data.username; renderCurrentUser(); return true; } return false; }
async function init(){
  const meRes = await api('/api/me', { method:'GET', headers:{} });
  if(meRes.success) state.me = meRes.user; else { const ok = await autoLogin(); if(!ok && !state.me) location.href='/login'; }
  renderCurrentUser(); bindNav();
  bindFile('inventoryFile','inventory'); bindFile('ordersFile','orders'); bindFile('masterFile','master'); bindFile('shipFile','ship');
  document.querySelectorAll('[data-submit]').forEach(btn => btn.addEventListener('click', ()=>submitPage(btn.dataset.submit)));
  document.querySelectorAll('[data-refresh]').forEach(btn => btn.addEventListener('click', () => { const p=btn.dataset.refresh; if(p==='inventory') refreshInventoryList(); if(p==='orders' || p==='master') refreshCustomersPanels(); if(p==='ship') refreshShipping(); }));
  document.querySelectorAll('[data-locate]').forEach(btn => btn.addEventListener('click', async ()=>{ const p=btn.dataset.locate; const text=$(p+'Text').value.trim(); const items=parseItemsFromText(text); const data = await api('/api/find_locations', { method:'POST', body: JSON.stringify({ items }) }); if(data.success){ $(p+'Result').innerHTML = (data.items||[]).map(x=>`<div>${escapeHtml(x.product)}｜${escapeHtml(x.location)}｜庫存:${x.quantity}</div>`).join('') || '沒有可反查的商品'; } }));
  $('refreshShipping').addEventListener('click', refreshShipping);
  $('refreshWarehouse').addEventListener('click', refreshWarehouse);
  $('refreshCustomers').addEventListener('click', refreshCustomersPanels);
  $('addWarehouseSlot').addEventListener('click', ()=>openSlotModal({slot_name:'', customer:'', product:'', quantity:0, note:''}));
  $('addCustomer').addEventListener('click', ()=>{ state.activeCustomer=null; $('customerModalTitle').textContent='新增客戶'; $('customerName').value=''; $('customerPhone').value=''; $('customerAddress').value=''; $('customerNotes').value=''; $('customerRegion').value='北區'; $('customerSort').value=0; $('customerProducts').innerHTML='新增後可點選編輯'; showModal('customerModal'); });
  $('saveCustomerBtn').addEventListener('click', saveCustomer);
  $('saveSlotBtn').addEventListener('click', saveSlot);
  $('deleteSlotBtn').addEventListener('click', async ()=>{ const name=$('slotName').value.trim(); if(!name) return; if(!confirm(`刪除 ${name}？`)) return; await fetch(`/api/warehouse_slots/${encodeURIComponent(name)}`, { method:'DELETE', credentials:'same-origin' }); hideModal('warehouseModal'); await refreshWarehouse(); });
  $('openSettingsBtn').addEventListener('click', ()=>{ showModal('settingsModal'); refreshSettings(); });
  $('savePasswordBtn').addEventListener('click', async ()=>{ const old_password=$('oldPassword').value.trim(); const new_password=$('newPassword').value.trim(); const data = await api('/api/change_password', { method:'POST', body: JSON.stringify({ old_password, new_password }) }); if(data.success){ alert('密碼已更新'); hideModal('settingsModal'); } else alert(data.error || '失敗'); });
  $('logoutBtn').addEventListener('click', async ()=>{ await fetch('/api/logout', { method:'POST', credentials:'same-origin' }); localStorage.removeItem('password'); location.href='/login'; });
  document.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', ()=>hideModal(btn.dataset.close)));
  $('customerModal').addEventListener('click', e => { if(e.target.id==='customerModal') hideModal('customerModal'); });
  $('warehouseModal').addEventListener('click', e => { if(e.target.id==='warehouseModal') hideModal('warehouseModal'); });
  $('settingsModal').addEventListener('click', e => { if(e.target.id==='settingsModal') hideModal('settingsModal'); });
  await refreshCustomersPanels(); await refreshShipping(); await refreshWarehouse(); await refreshInventoryList();
}
document.addEventListener('DOMContentLoaded', init);
