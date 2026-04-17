
const state = {
  module: null,
  rememberLogin: true,
  lastOcrItems: [],
  warehouse: { cells: [], zones: null, availableItems: [] },
  currentCell: null,
  currentCellItems: [],
  currentCustomer: null,
  customerItems: []
};

function $(id){ return document.getElementById(id); }
function qs(sel){ return document.querySelector(sel); }
function qsa(sel){ return Array.from(document.querySelectorAll(sel)); }

async function requestJSON(url, options={}){
  const res = await fetch(url, {
    headers: {'Content-Type': 'application/json', ...(options.headers||{})},
    ...options
  });
  const data = await res.json().catch(()=>({success:false,error:'回應解析失敗'}));
  if(!res.ok || data.success === false){
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

function toast(msg, kind=''){
  let t = $('toast');
  if(!t){
    t = document.createElement('div');
    t.id='toast';
    t.className='toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(()=>{ t.className='toast'; }, 2400);
}

function currentModule(){
  const el = qs('.module-screen');
  return el ? el.dataset.module : null;
}

document.addEventListener('DOMContentLoaded', () => {
  state.module = currentModule();
  if ($('remember-label')) {
    state.rememberLogin = localStorage.getItem('rememberLogin') !== '0';
    $('remember-label').textContent = state.rememberLogin ? '開' : '關';
  }
  if ($('login-username')) {
    initLoginPage();
  }
  if ($('old-password')) {
    // settings page
  }
  if (state.module) {
    initModulePage();
  }
});

function initLoginPage(){
  const u = localStorage.getItem('username') || '';
  const p = localStorage.getItem('password') || '';
  if ($('login-username')) $('login-username').value = u;
  if ($('login-password')) $('login-password').value = p;
  if (u && p) {
    submitLogin(true);
  }
  const pass = $('login-password');
  if (pass) pass.addEventListener('keypress', e => { if (e.key === 'Enter') submitLogin(); });
}

function toggleLoginSave(){
  state.rememberLogin = !state.rememberLogin;
  localStorage.setItem('rememberLogin', state.rememberLogin ? '1' : '0');
  if ($('remember-label')) $('remember-label').textContent = state.rememberLogin ? '開' : '關';
}

async function submitLogin(auto=false){
  const username = ($('login-username')?.value || '').trim();
  const password = ($('login-password')?.value || '').trim();
  const err = $('login-error');
  if (!username || !password) {
    if (!auto && err) { err.textContent = '請輸入帳號與密碼'; err.classList.remove('hidden'); }
    return;
  }
  try {
    const data = await requestJSON('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    localStorage.setItem('username', username);
    localStorage.setItem('password', password);
    if (state.rememberLogin) {
      localStorage.setItem('username', username);
      localStorage.setItem('password', password);
    }
    if (err) err.classList.add('hidden');
    window.location.href = '/';
  } catch (e) {
    if (err) {
      err.textContent = e.message || '登入失敗';
      err.classList.remove('hidden');
    }
  }
}

async function logout(){
  try { await requestJSON('/api/logout', { method:'POST', body:'{}' }); } catch(e){}
  localStorage.removeItem('username');
  localStorage.removeItem('password');
  window.location.href = '/login';
}

async function changePassword(){
  const old_password = ($('old-password')?.value || '').trim();
  const new_password = ($('new-password')?.value || '').trim();
  const confirm_password = ($('confirm-password')?.value || '').trim();
  const msg = $('settings-msg');
  try {
    await requestJSON('/api/change_password', {
      method: 'POST',
      body: JSON.stringify({ old_password, new_password, confirm_password })
    });
    if (msg) { msg.textContent = '密碼已更新'; msg.classList.remove('hidden'); }
    toast('密碼修改成功', 'ok');
    $('old-password').value = $('new-password').value = $('confirm-password').value = '';
  } catch (e) {
    if (msg) { msg.textContent = e.message; msg.classList.remove('hidden'); }
  }
}

function initModulePage(){
  const module = state.module;
  setupUploadButtons();
  const album = $('album-input');
  const camera = $('camera-input');
  if (album) album.addEventListener('change', e => handleFiles(e.target.files));
  if (camera) camera.addEventListener('change', e => handleFiles(e.target.files));

  if (module === 'inventory') loadInventory();
  if (module === 'orders' || module === 'master_order' || module === 'ship') loadCustomerBlocks();
  if (module === 'shipping_query') loadShippingRecords();
  if (module === 'warehouse') renderWarehouse();
  if (module === 'customers') renderCustomers();
}

function setupUploadButtons(){
  // nothing else; native picker behavior via hidden input
}

function openAlbumPicker(){ $('album-input')?.click(); }
function openCameraPicker(){ $('camera-input')?.click(); }
function resetModuleForm(){
  if ($('ocr-text')) $('ocr-text').value = '';
  if ($('customer-name')) $('customer-name').value = '';
  if ($('location-input')) $('location-input').value = '';
  if ($('ocr-confidence-pill')) $('ocr-confidence-pill').textContent = '信心值：0%';
  if ($('ocr-warning-pill')) $('ocr-warning-pill').textContent = '尚未辨識';
  if ($('module-result')) { $('module-result').classList.add('hidden'); $('module-result').innerHTML = ''; }
}

async function handleFiles(fileList){
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const file = files[0];
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/upload_ocr', { method:'POST', body: form });
    const data = await res.json();
    if (!res.ok || data.success === false) throw new Error(data.error || 'OCR失敗');
    if ($('ocr-text')) $('ocr-text').value = data.text || '';
    if ($('ocr-confidence-pill')) $('ocr-confidence-pill').textContent = `信心值：${data.confidence || 0}%`;
    if ($('ocr-warning-pill')) $('ocr-warning-pill').textContent = data.warning || '辨識完成';
    state.lastOcrItems = data.items || [];
    if (data.warning) toast(data.warning, 'warn');
    else toast('OCR辨識完成', 'ok');
  } catch (e) {
    if ($('ocr-warning-pill')) $('ocr-warning-pill').textContent = e.message;
    toast(e.message || 'OCR辨識失敗', 'error');
  }
}

function parseTextareaItems(){
  const text = ($('ocr-text')?.value || '').trim();
  if (!text) return [];
  const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean);
  return lines.map(line => {
    const parts = line.split(/[:=]/);
    let product_text = line, qty = 1, product_code = '';
    if (parts.length >= 2) {
      product_text = parts[0].trim();
      qty = parseInt(parts[1], 10) || 1;
    } else {
      const m = line.match(/^(.+?)[x\*](\d+)$/i);
      if (m) { product_text = m[1].trim(); qty = parseInt(m[2], 10) || 1; }
    }
    product_code = product_text.split('=')[0];
    return { product_text, product_code, qty };
  });
}

async function confirmSubmit(){
  const module = state.module;
  const customer_name = ($('customer-name')?.value || '').trim();
  const location = ($('location-input')?.value || '').trim();
  const ocr_text = ($('ocr-text')?.value || '').trim();
  const items = state.lastOcrItems && state.lastOcrItems.length ? state.lastOcrItems : parseTextareaItems();
  try {
    let endpoint = '/api/inventory';
    if (module === 'orders') endpoint = '/api/orders';
    if (module === 'master_order') endpoint = '/api/master_orders';
    if (module === 'ship') endpoint = '/api/ship';
    const payload = { customer_name, location, ocr_text, items };
    const data = await requestJSON(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    renderSubmitResult(module, data, customer_name);
    if (module === 'inventory') await loadInventory();
    if (module === 'orders' || module === 'master_order' || module === 'ship') await loadCustomerBlocks();
    if (module === 'warehouse') await renderWarehouse();
    toast('送出完成', 'ok');
  } catch (e) {
    showResult(`錯誤：${e.message}`, true);
  }
}

function renderSubmitResult(module, data, customerName=''){
  const box = $('module-result');
  if (!box) return;
  box.classList.remove('hidden');
  let html = '';
  if (module === 'ship') {
    const breakdown = data.breakdown || [];
    html += `<div class="section-title">出貨結果</div>`;
    html += `<div class="muted">客戶：${escapeHTML(customerName)}</div>`;
    breakdown.forEach(b => {
      html += `<div class="chip-item"><strong>${escapeHTML(b.product_text)}</strong> × ${b.qty} ｜ 總單 ${b.master_deduct} ｜ 訂單 ${b.order_deduct} ｜ 庫存 ${b.inventory_deduct}</div>`;
    });
  } else if (module === 'orders') {
    html += `<div class="section-title">訂單已建立</div><div class="muted">客戶：${escapeHTML(customerName)}｜狀態：pending</div>`;
  } else if (module === 'master_order') {
    html += `<div class="section-title">總單已更新</div><div class="muted">客戶：${escapeHTML(customerName)}</div>`;
  } else if (module === 'inventory') {
    html += `<div class="section-title">庫存已更新</div>`;
  } else {
    html += `<div class="section-title">已儲存</div>`;
  }
  box.innerHTML = html;
}

function showResult(msg, isError=false){
  const box = $('module-result');
  if (!box) return;
  box.classList.remove('hidden');
  box.innerHTML = `<div class="${isError ? 'warning-red' : ''}">${msg}</div>`;
}

async function loadInventory(){
  try {
    const data = await requestJSON('/api/inventory', { method:'GET' });
    const el = $('inventory-summary');
    if (!el) return;
    el.innerHTML = '';
    (data.items || []).forEach(item => {
      const card = document.createElement('div');
      card.className = `card ${item.needs_red ? 'red' : ''}`;
      card.innerHTML = `
        <div class="title ${item.needs_red ? 'warning-red' : ''}">${escapeHTML(item.product_text || '')}</div>
        <div class="sub">總數量：${item.qty || 0}</div>
        <div class="sub">已放倉庫：${item.placed_qty || 0}</div>
        <div class="sub">未放倉庫：${item.unplaced_qty || 0}</div>
        <div class="sub">客戶：${escapeHTML(item.customer_name || '—')}</div>
        <div class="sub">位置：${escapeHTML(item.location || '—')}</div>
      `;
      el.appendChild(card);
    });
  } catch (e) {
    console.error(e);
  }
}

async function loadCustomerBlocks(){
  try {
    const data = await requestJSON('/api/customers', { method:'GET' });
    const groups = { '北區': $('region-north'), '中區': $('region-center'), '南區': $('region-south') };
    if ($('customers-north')) groups['北區'] = $('customers-north');
    if ($('customers-center')) groups['中區'] = $('customers-center');
    if ($('customers-south')) groups['南區'] = $('customers-south');
    Object.values(groups).forEach(el => { if (el) el.innerHTML=''; });
    const q = ($('customer-search')?.value || '').trim().toLowerCase();
    (data.items || []).filter(c => !q || (c.name || '').toLowerCase().includes(q)).forEach(c => {
      const chip = document.createElement('div');
      chip.className = 'chip';
      chip.draggable = true;
      chip.dataset.customer = c.name;
      chip.innerHTML = `<span>${escapeHTML(c.name)}</span>`;
      chip.addEventListener('dragstart', ev => {
        ev.dataTransfer.setData('text/plain', JSON.stringify({name:c.name, region:c.region || '北區'}));
      });
      chip.addEventListener('click', () => openCustomerModal(c.name));
      const target = groups[c.region || '北區'] || groups['北區'];
      target?.appendChild(chip);
    });
    setupCustomerDropZones();
    if (state.module === 'customers') {
      $('cust-region').value = '北區';
      if (! $('cust-name').value) {
        $('cust-name').placeholder = '點選客戶可自動帶入';
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function setupCustomerDropZones(){
  qsa('.category-box').forEach(box => {
    box.ondragover = e => { e.preventDefault(); box.classList.add('drag-over'); };
    box.ondragleave = () => box.classList.remove('drag-over');
    box.ondrop = async e => {
      e.preventDefault(); box.classList.remove('drag-over');
      const data = JSON.parse(e.dataTransfer.getData('text/plain'));
      if (!data || !data.name) return;
      try {
        await requestJSON('/api/customers', { method:'POST', body: JSON.stringify({ name:data.name, region: box.dataset.region }) });
        toast('客戶分類已更新', 'ok');
        loadCustomerBlocks();
      } catch(err){ toast(err.message, 'error'); }
    };
  });
}

async function openCustomerModal(name){
  try {
    state.currentCustomer = name;
    const detail = await requestJSON(`/api/customers/${encodeURIComponent(name)}`, { method:'GET' });
    const items = await requestJSON(`/api/customer-items?name=${encodeURIComponent(name)}`, { method:'GET' });
    $('customer-modal').classList.remove('hidden');
    const body = $('customer-modal-body');
    body.innerHTML = `
      <div class="card-list">
        <div class="card">
          <div class="title">${escapeHTML(name)}</div>
          <div class="sub">電話：${escapeHTML(detail.item?.phone || '')}</div>
          <div class="sub">地址：${escapeHTML(detail.item?.address || '')}</div>
          <div class="sub">特殊要求：${escapeHTML(detail.item?.notes || '')}</div>
          <div class="sub">區域：${escapeHTML(detail.item?.region || '')}</div>
        </div>
        <div class="card">
          <div class="title">商品</div>
          <div id="customer-modal-items" class="chip-list"></div>
        </div>
      </div>`;
    const list = $('customer-modal-items');
    (items.items || []).forEach(it => {
      const ch = document.createElement('div');
      ch.className='chip-item';
      ch.textContent = `${it.source}｜${it.product_text || ''} × ${it.qty || 0}`;
      list.appendChild(ch);
    });
    $('cust-name').value = detail.item?.name || name;
    $('cust-phone').value = detail.item?.phone || '';
    $('cust-address').value = detail.item?.address || '';
    $('cust-notes').value = detail.item?.notes || '';
    $('cust-region').value = detail.item?.region || '北區';
  } catch (e) {
    toast(e.message, 'error');
  }
}

function closeCustomerModal(){ $('customer-modal')?.classList.add('hidden'); }

async function saveCustomer(){
  try {
    const payload = {
      name: ($('cust-name')?.value || '').trim(),
      phone: ($('cust-phone')?.value || '').trim(),
      address: ($('cust-address')?.value || '').trim(),
      notes: ($('cust-notes')?.value || '').trim(),
      region: $('cust-region')?.value || '北區'
    };
    await requestJSON('/api/customers', { method:'POST', body: JSON.stringify(payload) });
    toast('客戶已儲存', 'ok');
    await loadCustomerBlocks();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadShippingRecords(){
  try {
    const range = $('ship-range')?.value || '7';
    let start = $('ship-start')?.value;
    let end = $('ship-end')?.value;
    if (range !== 'custom') {
      const days = parseInt(range, 10) || 7;
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(endDate.getDate() - days + 1);
      end = endDate.toISOString().slice(0,10);
      start = startDate.toISOString().slice(0,10);
      if ($('ship-start')) $('ship-start').value = start;
      if ($('ship-end')) $('ship-end').value = end;
    }
    const qs = new URLSearchParams();
    if (start) qs.set('start_date', start);
    if (end) qs.set('end_date', end);
    const data = await requestJSON(`/api/shipping_records?${qs.toString()}`, { method:'GET' });
    const el = $('shipping-results');
    if (!el) return;
    if (!data.records || !data.records.length) {
      el.innerHTML = '<div class="panel">沒有資料</div>';
      return;
    }
    let html = '<table><thead><tr><th>客戶</th><th>商品</th><th>數量</th><th>操作人員</th><th>出貨時間</th></tr></thead><tbody>';
    data.records.forEach(r => {
      html += `<tr><td>${escapeHTML(r.customer_name || '')}</td><td>${escapeHTML(r.product_text || '')}</td><td>${r.qty || 0}</td><td>${escapeHTML(r.operator || '')}</td><td>${escapeHTML(r.shipped_at || '')}</td></tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  } catch (e) {
    const el = $('shipping-results');
    if (el) el.innerHTML = `<div class="panel warning-red">${e.message}</div>`;
  }
}

async function renderWarehouse(){
  try {
    const [data, avail] = await Promise.all([
      requestJSON('/api/warehouse', { method:'GET' }),
      requestJSON('/api/warehouse/available-items', { method:'GET' })
    ]);
    state.warehouse.cells = data.cells || [];
    state.warehouse.zones = data.zones || {};
    state.warehouse.availableItems = avail.items || [];
    renderWarehouseZones();
  } catch (e) {
    console.error(e);
  }
}

function buildCellKey(zone, column_index, slot_type, slot_number){
  return [zone, column_index, slot_type, slot_number];
}

function getCellItems(zone, column_index, slot_type, slot_number){
  const cell = state.warehouse.cells.find(c => c.zone === zone && parseInt(c.column_index) === parseInt(column_index) && c.slot_type === slot_type && parseInt(c.slot_number) === parseInt(slot_number));
  if (!cell) return [];
  try { return JSON.parse(cell.items_json || '[]'); } catch(e){ return []; }
}

function renderWarehouseZones(){
  const renderZone = (zone) => {
    const wrap = $(`zone-${zone}-grid`);
    if (!wrap) return;
    wrap.innerHTML = '';
    for (let c = 1; c <= 12; c++) {
      const col = document.createElement('div');
      col.className = 'column-card';
      col.innerHTML = `<div class="column-head">${zone} ${c}</div>`;
      ['front', 'back'].forEach(side => {
        const row = document.createElement('div');
        row.className = 'slot-row';
        for (let n=1; n<=10; n++) {
          const slot = document.createElement('div');
          slot.className = 'slot';
          slot.dataset.zone = zone;
          slot.dataset.column = c;
          slot.dataset.side = side;
          slot.dataset.num = n;
          const items = getCellItems(zone, c, side, n);
          slot.innerHTML = `<div class="slot-title">${side === 'front' ? '前' : '後'} ${n}</div><div class="slot-count">${items.length ? `${items.length} 筆` : '空'}</div>`;
          if (items.length) {
            const first = items[0];
            slot.innerHTML += `<div class="slot-chip" draggable="true">${escapeHTML(first.product_text || first.product || '')} × ${first.qty || 0}</div>`;
            slot.classList.add('filled');
          }
          slot.addEventListener('click', () => openWarehouseModal(zone, c, side, n));
          slot.addEventListener('dragover', ev => { ev.preventDefault(); slot.classList.add('drag-over'); });
          slot.addEventListener('dragleave', () => slot.classList.remove('drag-over'));
          slot.addEventListener('drop', async ev => {
            ev.preventDefault(); slot.classList.remove('drag-over');
            const raw = ev.dataTransfer.getData('text/plain');
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (parsed.kind === 'warehouse-item') {
              await moveWarehouseItem(parsed.fromKey, buildCellKey(zone, c, side, n), parsed.product_text, parsed.qty);
            }
          });
          row.appendChild(slot);
        }
        col.appendChild(row);
      });
      wrap.appendChild(col);
    }
  };
  renderZone('A');
  renderZone('B');
}

async function openWarehouseModal(zone, column, side, num){
  state.currentCell = { zone, column, slot_type: side, slot_number: num };
  state.currentCellItems = getCellItems(zone, column, side, num);
  $('warehouse-modal').classList.remove('hidden');
  $('warehouse-modal-meta').textContent = `${zone} 區 / 第 ${column} 欄 / ${side === 'front' ? '前' : '後'} / ${num}`;
  $('warehouse-note').value = (state.warehouse.cells.find(c => c.zone===zone && parseInt(c.column_index)===parseInt(column) && c.slot_type===side && parseInt(c.slot_number)===parseInt(num)) || {}).note || '';
  renderWarehouseCellItems();
  refreshWarehouseSelect();
  const search = $('warehouse-item-search');
  if (search) search.oninput = refreshWarehouseSelect;
}

function closeWarehouseModal(){ $('warehouse-modal')?.classList.add('hidden'); }

function refreshWarehouseSelect(){
  const sel = $('warehouse-item-select');
  if (!sel) return;
  const q = ($('warehouse-item-search')?.value || '').trim().toLowerCase();
  sel.innerHTML = '';
  state.warehouse.availableItems.filter(it => !q || `${it.product_text} ${it.customer_name || ''}`.toLowerCase().includes(q)).forEach(it => {
    const opt = document.createElement('option');
    opt.value = JSON.stringify(it);
    opt.textContent = `${it.product_text}｜剩餘 ${it.unplaced_qty}`;
    sel.appendChild(opt);
  });
  if (!sel.options.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = '沒有可加入的商品';
    sel.appendChild(opt);
  }
}

function renderWarehouseCellItems(){
  const list = $('warehouse-cell-items');
  if (!list) return;
  list.innerHTML = '';
  state.currentCellItems.forEach((it, idx) => {
    const chip = document.createElement('div');
    chip.className = 'chip-item';
    chip.draggable = true;
    chip.dataset.idx = idx;
    chip.innerHTML = `<span>${escapeHTML(it.product_text || '')} × ${it.qty || 0}${it.customer_name ? ` ｜ ${escapeHTML(it.customer_name)}` : ''}</span>
      <button class="remove" data-idx="${idx}">刪除</button>`;
    chip.addEventListener('dragstart', ev => {
      ev.dataTransfer.setData('text/plain', JSON.stringify({
        kind: 'warehouse-item',
        fromKey: buildCellKey(state.currentCell.zone, state.currentCell.column, state.currentCell.slot_type, state.currentCell.slot_number),
        product_text: it.product_text || '',
        qty: it.qty || 1
      }));
    });
    chip.querySelector('.remove').addEventListener('click', () => {
      state.currentCellItems.splice(idx, 1);
      renderWarehouseCellItems();
    });
    list.appendChild(chip);
  });
}

function addSelectedItemToCell(){
  const sel = $('warehouse-item-select');
  if (!sel || !sel.value) return;
  const item = JSON.parse(sel.value);
  const qty = Math.max(1, parseInt(($('warehouse-add-qty')?.value || '1'), 10) || 1);
  state.currentCellItems.push({
    product_text: item.product_text,
    product_code: item.product_code || '',
    qty,
    customer_name: item.customer_name || '',
    source: 'inventory'
  });
  renderWarehouseCellItems();
}

async function saveWarehouseCell(){
  if (!state.currentCell) return;
  try {
    const note = $('warehouse-note')?.value || '';
    await requestJSON('/api/warehouse/cell', {
      method: 'POST',
      body: JSON.stringify({
        ...state.currentCell,
        items: state.currentCellItems,
        note
      })
    });
    toast('格位已儲存', 'ok');
    closeWarehouseModal();
    await renderWarehouse();
    await loadInventory();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function moveWarehouseItem(fromKey, toKey, product_text, qty){
  try {
    await requestJSON('/api/warehouse/move', {
      method: 'POST',
      body: JSON.stringify({ from_key: fromKey, to_key: toKey, product_text, qty })
    });
    toast('已拖曳移動', 'ok');
    await renderWarehouse();
    await loadInventory();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function searchWarehouse(){
  const q = ($('warehouse-search')?.value || '').trim();
  if (!q) {
    await renderWarehouse();
    return;
  }
  try {
    const data = await requestJSON(`/api/warehouse/search?q=${encodeURIComponent(q)}`, { method:'GET' });
    const box = $('warehouse-search-results');
    if (!box) return;
    box.classList.remove('hidden');
    if (!data.items || !data.items.length) {
      box.innerHTML = '<div class="search-card">沒有找到資料</div>';
      return;
    }
    box.innerHTML = '';
    data.items.forEach(r => {
      const cell = r.cell;
      const item = r.item;
      const div = document.createElement('div');
      div.className = 'search-card';
      div.innerHTML = `<strong>${escapeHTML(cell.zone)}區 ${cell.column_index} / ${cell.slot_type} / ${cell.slot_number}</strong><br>${escapeHTML(item.product_text || '')} × ${item.qty || 0}`;
      box.appendChild(div);
    });
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function reverseLookup(){
  const q = ($('ocr-text')?.value || $('customer-name')?.value || '').trim();
  if (!q) return;
  if (state.module === 'warehouse') {
    $('warehouse-search').value = q.split(/\s+/)[0];
    searchWarehouse();
  } else {
    toast('已幫你抓取查詢條件', 'ok');
  }
}

async function renderCustomers(){
  if (state.module !== 'customers') return;
  await loadCustomerBlocks();
}

function escapeHTML(str){
  return String(str ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
}

// expose globals
window.openAlbumPicker = openAlbumPicker;
window.openCameraPicker = openCameraPicker;
window.resetModuleForm = resetModuleForm;
window.confirmSubmit = confirmSubmit;
window.reverseLookup = reverseLookup;
window.logout = logout;
window.submitLogin = submitLogin;
window.toggleLoginSave = toggleLoginSave;
window.changePassword = changePassword;
window.openCustomerModal = openCustomerModal;
window.closeCustomerModal = closeCustomerModal;
window.saveCustomer = saveCustomer;
window.loadShippingRecords = loadShippingRecords;
window.searchWarehouse = searchWarehouse;
window.closeWarehouseModal = closeWarehouseModal;
window.addSelectedItemToCell = addSelectedItemToCell;
window.saveWarehouseCell = saveWarehouseCell;
window.renderWarehouse = renderWarehouse;
window.renderCustomers = renderCustomers;
