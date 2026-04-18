const state = {
  user: null,
  summary: { added_count: 0, shipped_count: 0, unassigned_count: 0, unread_count: 0 },
  inventory: [],
  orders: [],
  masterItems: [],
  slots: [],
  logs: [],
  currentView: 'home',
  highlightSlotLabel: '',
  ocr: {
    image: null,
    imagePath: '',
    selectedRect: null,
    naturalWidth: 0,
    naturalHeight: 0,
  },
  installPrompt: null,
};

const dialog = {
  node: null,
  title: null,
  content: null,
  submit: null,
  onSubmit: null,
};

const throttle = {
  refreshTimer: null,
};

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function showToast(message) {
  const container = el('toastContainer');
  const node = document.createElement('div');
  node.className = 'toast';
  node.textContent = message;
  container.appendChild(node);
  setTimeout(() => {
    node.remove();
  }, 2400);
}

async function api(path, options = {}) {
  const config = { ...options };
  config.headers = config.headers || {};
  if (config.body && !(config.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  const data = await response.json().catch(() => ({ ok: false, error: '伺服器回應格式錯誤' }));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || '發生錯誤');
  }
  return data;
}

function setTodayLabel() {
  el('todayLabel').textContent = new Date().toLocaleDateString('zh-TW');
}

function updateHeader() {
  el('summaryAdded').textContent = state.summary.added_count ?? 0;
  el('summaryShipped').textContent = state.summary.shipped_count ?? 0;
  el('summaryUnassigned').textContent = state.summary.unassigned_count ?? 0;
  el('todayAdded').textContent = state.summary.added_count ?? 0;
  el('todayShipped').textContent = state.summary.shipped_count ?? 0;
  el('todayUnassigned').textContent = state.summary.unassigned_count ?? 0;
  el('usernameBelow').textContent = state.user ? `登入使用者：${state.user.username}` : '';
  const badge = el('todayBadge');
  const unread = Number(state.summary.unread_count || 0);
  badge.textContent = unread;
  badge.classList.toggle('hidden', unread <= 0);
}

function setView(viewName, options = {}) {
  state.currentView = viewName;
  document.querySelectorAll('.view').forEach((node) => node.classList.remove('active'));
  const target = el(`view-${viewName}`);
  if (target) target.classList.add('active');

  if (viewName === 'today' && !options.skipMarkRead) {
    markTodayRead();
  }
  if (viewName === 'warehouse') {
    renderWarehouse();
  }
}

async function loadMe() {
  const data = await api('/api/auth/me');
  state.user = data.user;
  el('loginScreen').classList.toggle('hidden', !!state.user);
  el('appShell').classList.toggle('hidden', !state.user);
  if (state.user) {
    updateHeader();
  }
}

async function loadSummary() {
  const data = await api('/api/activity/summary');
  state.summary = data.summary;
  updateHeader();
}

async function loadInventory() {
  const search = el('inventorySearch').value.trim();
  const data = await api(`/api/inventory${search ? `?search=${encodeURIComponent(search)}` : ''}`);
  state.inventory = data.items;
  renderInventory();
  renderToday();
}

async function loadOrders() {
  const data = await api('/api/orders');
  state.orders = data.orders;
  renderOrders();
}

async function loadMasterOrders() {
  const data = await api('/api/master-orders');
  state.masterItems = data.items;
  renderMaster();
}

async function loadWarehouse() {
  const data = await api('/api/warehouse/slots');
  state.slots = data.slots;
  renderWarehouse();
}

async function loadLogs() {
  const data = await api('/api/activity/logs');
  state.logs = data.logs;
  renderToday();
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadInventory(), loadOrders(), loadMasterOrders(), loadWarehouse(), loadLogs()]);
}

function queueRefresh() {
  window.clearTimeout(throttle.refreshTimer);
  throttle.refreshTimer = window.setTimeout(() => {
    refreshAll().catch((error) => showToast(error.message));
  }, 250);
}

async function login(username, password) {
  const data = await api('/api/auth/login', { method: 'POST', body: { username, password } });
  state.user = data.user;
  el('loginScreen').classList.add('hidden');
  el('appShell').classList.remove('hidden');
  setTodayLabel();
  updateHeader();
  await refreshAll();
  setView('home');
  showToast(`已登入：${state.user.username}`);
}

async function logout() {
  await api('/api/auth/logout', { method: 'POST' });
  state.user = null;
  el('appShell').classList.add('hidden');
  el('loginScreen').classList.remove('hidden');
}

function openDialog({ title, html, submitText = '儲存', onSubmit }) {
  dialog.title.textContent = title;
  dialog.content.innerHTML = html;
  dialog.submit.textContent = submitText;
  dialog.onSubmit = onSubmit;
  dialog.node.showModal();
}

function closeDialog() {
  dialog.node.close();
}

function renderInventory() {
  const container = el('inventoryList');
  if (!state.inventory.length) {
    container.innerHTML = `<div class="panel-card" style="padding:18px">目前沒有庫存資料。</div>`;
    return;
  }

  container.innerHTML = state.inventory.map((item) => {
    const slotText = item.slot_label ? `倉位：${escapeHtml(item.slot_label)}` : '未錄入倉庫圖';
    const confidence = Number(item.ocr_confidence || 0).toFixed(2);
    return `
      <article class="inventory-card">
        <div class="card-top">
          <div>
            <div class="card-title">${escapeHtml(item.product_name)}</div>
            <div class="card-sub">${escapeHtml(item.spec || '無規格')}</div>
          </div>
          <div class="status-pill ${item.is_unassigned ? 'status-danger' : ''}">
            ${escapeHtml(slotText)}
          </div>
        </div>
        <div class="small-note">數量：${item.quantity} ${escapeHtml(item.unit || '件')} ｜ OCR 信心值：${confidence}</div>
        <div class="small-note">${escapeHtml(item.note || '')}</div>
        <div class="card-actions">
          <button class="btn btn-primary" onclick="openAddToOrderDialog(${item.id})">加入訂單</button>
          <button class="btn btn-secondary" onclick="openInventoryEditDialog(${item.id})">編輯</button>
          <button class="btn btn-secondary" onclick="openAssignSlotDialog(${item.id})">${item.slot_label ? '更換倉位' : '配置倉位'}</button>
          <button class="btn btn-secondary" onclick="locateInventory(${item.id})">找位置</button>
          <button class="btn btn-secondary" onclick="deleteInventory(${item.id})">刪除</button>
        </div>
      </article>
    `;
  }).join('');
}

function renderOrders() {
  const container = el('ordersList');
  if (!state.orders.length) {
    container.innerHTML = `<div class="panel-card" style="padding:18px">目前沒有訂單。</div>`;
    return;
  }

  container.innerHTML = state.orders.map((order) => `
    <article class="order-card">
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(order.customer_name)}</div>
          <div class="card-sub">狀態：${escapeHtml(order.status)}</div>
        </div>
        <div class="status-pill">${escapeHtml(order.status)}</div>
      </div>
      <div class="card-list compact">
        ${order.items.map((item) => `
          <div class="panel-card" style="padding:14px">
            <div class="card-top">
              <div>
                <div class="card-title" style="font-size:18px">${escapeHtml(item.product_name)}</div>
                <div class="card-sub">${escapeHtml(item.spec || '無規格')}</div>
              </div>
              <div class="status-pill ${item.status === 'shipped' ? '' : 'status-danger'}">${escapeHtml(item.status)}</div>
            </div>
            <div class="small-note">數量：${item.quantity} ${escapeHtml(item.unit || '件')} ｜ 倉位：${escapeHtml(item.slot_label || '未配置')}</div>
            <div class="card-actions">
              <button class="btn btn-secondary" onclick="openOrderEditDialog(${item.id})">修改</button>
              <button class="btn btn-secondary" onclick="cancelOrderItem(${item.id})">取消</button>
              <button class="btn btn-primary" onclick="shipOrderItem(${item.id})">出貨</button>
              <button class="btn btn-secondary" onclick="addOrderItemToMaster(${item.id})">加入總單</button>
              <button class="btn btn-secondary" onclick="locateOrderItem(${item.id})">跳到倉庫圖</button>
            </div>
          </div>
        `).join('')}
      </div>
    </article>
  `).join('');
}

function renderMaster() {
  const container = el('masterList');
  if (!state.masterItems.length) {
    container.innerHTML = `<div class="panel-card" style="padding:18px">目前沒有總單資料。</div>`;
    return;
  }
  container.innerHTML = state.masterItems.map((item) => `
    <article class="master-card">
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(item.product_name)}</div>
          <div class="card-sub">${escapeHtml(item.spec || '無規格')}</div>
        </div>
        <div class="status-pill">總數：${item.quantity}${escapeHtml(item.unit || '件')}</div>
      </div>
      <div class="small-note">${escapeHtml(item.note || '')}</div>
      <div class="card-actions">
        <button class="btn btn-secondary" onclick="deleteMasterItem(${item.id})">刪除</button>
      </div>
    </article>
  `).join('');
}

function getZones() {
  const zoneMap = {};
  state.slots.forEach((slot) => {
    if (!zoneMap[slot.zone]) zoneMap[slot.zone] = [];
    zoneMap[slot.zone].push(slot);
  });
  return zoneMap;
}

function slotMatchesSearch(slot, search) {
  if (!search) return false;
  const value = `${slot.label} ${slot.item?.product_name || ''} ${slot.item?.spec || ''}`.toLowerCase();
  return value.includes(search.toLowerCase());
}

function renderWarehouse() {
  const container = el('warehouseMap');
  const zoneMap = getZones();
  const search = el('warehouseSearch').value.trim();
  const zoneNames = Object.keys(zoneMap).sort();

  if (!zoneNames.length) {
    container.innerHTML = `<div class="panel-card" style="padding:18px">沒有倉位資料。</div>`;
    return;
  }

  container.innerHTML = zoneNames.map((zone) => {
    const slots = zoneMap[zone];
    const grouped = {};
    slots.forEach((slot) => {
      if (!grouped[slot.band]) grouped[slot.band] = { front: [], back: [] };
      grouped[slot.band][slot.row].push(slot);
    });

    const bands = Object.keys(grouped).sort((a, b) => Number(a) - Number(b));
    return `
      <section class="zone-card">
        <div class="zone-title">${escapeHtml(zone)} 區</div>
        ${bands.map((band) => {
          const front = grouped[band].front.sort((a, b) => a.col_index - b.col_index);
          const back = grouped[band].back.sort((a, b) => a.col_index - b.col_index);
          return `
            <div class="band-row">
              <div class="band-index">${band}</div>
              ${renderRowGrid(front, search)}
              ${renderRowGrid(back, search)}
            </div>
          `;
        }).join('')}
      </section>
    `;
  }).join('');

  attachWarehouseDragEvents();
}

function renderRowGrid(slots, search) {
  return `
    <div class="row-grid">
      ${slots.map((slot) => {
        const hasItem = !!slot.item;
        const cls = hasItem ? 'used' : 'empty';
        const highlighted = state.highlightSlotLabel && slot.label === state.highlightSlotLabel ? 'highlight' : '';
        const searchHit = slotMatchesSearch(slot, search) ? 'search-hit' : '';
        return `
          <button
            class="slot-card ${cls} ${highlighted} ${searchHit}"
            data-slot-id="${slot.id}"
            data-slot-label="${escapeHtml(slot.label)}"
            data-item-id="${slot.item ? slot.item.id : ''}"
            draggable="${hasItem ? 'true' : 'false'}"
            onclick="openSlotDialog(${slot.id})"
          >
            <div class="slot-top">
              <span>${escapeHtml(slot.label)}</span>
              <span>${slot.row === 'front' ? '前排' : '後排'}</span>
            </div>
            <div class="slot-item">
              ${hasItem ? `${escapeHtml(slot.item.product_name)}<br><span class="small-note">${escapeHtml(slot.item.spec || '')}</span>` : '空位'}
            </div>
            <div class="small-note">${hasItem ? `${slot.item.quantity}${escapeHtml(slot.item.unit || '件')}` : ''}</div>
          </button>
        `;
      }).join('')}
    </div>
  `;
}

function attachWarehouseDragEvents() {
  document.querySelectorAll('.slot-card').forEach((node) => {
    node.addEventListener('dragstart', (event) => {
      const itemId = node.dataset.itemId;
      if (!itemId) return event.preventDefault();
      event.dataTransfer.setData('text/plain', itemId);
    });
    node.addEventListener('dragover', (event) => event.preventDefault());
    node.addEventListener('drop', async (event) => {
      event.preventDefault();
      const itemId = event.dataTransfer.getData('text/plain');
      const slotId = node.dataset.slotId;
      if (!itemId || !slotId) return;
      try {
        await api('/api/warehouse/move', {
          method: 'POST',
          body: { inventory_item_id: Number(itemId), to_slot_id: Number(slotId) },
        });
        showToast('已移動格位');
        await refreshAll();
      } catch (error) {
        showToast(error.message);
      }
    });
  });
}

function renderToday() {
  const activityList = el('activityList');
  const unassignedList = el('unassignedList');
  const unassignedItems = state.inventory.filter((item) => item.is_unassigned);

  if (!unassignedItems.length) {
    unassignedList.innerHTML = '';
  } else {
    unassignedList.innerHTML = `
      <div class="panel-card" style="padding:16px">
        <div class="card-title" style="font-size:18px">未錄入倉庫圖明細</div>
        <div class="card-list compact" style="margin-top:12px">
          ${unassignedItems.map((item) => `
            <div class="panel-card" style="padding:12px">
              <div class="card-top">
                <div>
                  <div class="card-title" style="font-size:16px">${escapeHtml(item.product_name)}</div>
                  <div class="card-sub">${escapeHtml(item.spec || '無規格')}</div>
                </div>
                <div class="status-pill status-danger">${item.quantity}${escapeHtml(item.unit || '件')}</div>
              </div>
              <div class="card-actions">
                <button class="btn btn-secondary" onclick="openAssignSlotDialog(${item.id})">立即配置倉位</button>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  if (!state.logs.length) {
    activityList.innerHTML = `<div class="panel-card" style="padding:18px">目前沒有異動紀錄。</div>`;
    return;
  }

  activityList.innerHTML = state.logs.map((log) => `
    <article class="activity-card" onclick="handleLogClick(${log.id})">
      <div class="card-top">
        <div>
          <div class="card-title" style="font-size:18px">${escapeHtml(log.action_type)} ｜ ${escapeHtml(log.product_name || '系統')}</div>
          <div class="card-sub">${escapeHtml(log.actor)} ｜ ${new Date(log.created_at).toLocaleString('zh-TW')}</div>
        </div>
        <button class="btn btn-secondary" onclick="event.stopPropagation();deleteLog(${log.id})">刪除</button>
      </div>
      <div class="small-note">${escapeHtml(log.detail || '')}</div>
      <div class="small-note">客戶：${escapeHtml(log.customer_name || '-')} ｜ 倉位：${escapeHtml(log.slot_label || '-')}</div>
    </article>
  `).join('');
}

async function markTodayRead() {
  try {
    await api('/api/activity/mark-read', { method: 'POST' });
    state.summary.unread_count = 0;
    updateHeader();
  } catch (error) {
    showToast(error.message);
  }
}

function handleLogClick(logId) {
  const log = state.logs.find((row) => row.id === logId);
  if (!log) return;
  if (log.slot_label) {
    state.highlightSlotLabel = log.slot_label;
    setView('warehouse');
    renderWarehouse();
    return;
  }
  showToast(log.detail || '已打開異動詳情');
}

function buildInventoryOptions(selectedId = '') {
  const options = state.inventory.map((item) =>
    `<option value="${item.id}" ${Number(selectedId) === Number(item.id) ? 'selected' : ''}>${escapeHtml(item.product_name)} / ${escapeHtml(item.spec || '')} / ${item.quantity}${escapeHtml(item.unit || '件')}</option>`
  );
  return options.join('');
}

function buildSlotOptions(selectedId = '') {
  const options = state.slots.map((slot) =>
    `<option value="${slot.id}" ${Number(selectedId) === Number(slot.id) ? 'selected' : ''}>${escapeHtml(slot.label)} ${slot.item ? `(目前：${escapeHtml(slot.item.product_name)})` : ''}</option>`
  );
  return options.join('');
}

window.openAddToOrderDialog = function(itemId) {
  const item = state.inventory.find((row) => row.id === itemId);
  if (!item) return;
  openDialog({
    title: `加入訂單｜${item.product_name}`,
    html: `
      <label>客戶名稱<input id="dialogCustomer" type="text" placeholder="客戶名稱"></label>
      <label>數量<input id="dialogQty" type="number" min="1" max="${item.quantity}" value="1"></label>
      <label>備註<textarea id="dialogNote" rows="3"></textarea></label>
    `,
    submitText: '加入訂單',
    onSubmit: async () => {
      await api(`/api/inventory/${itemId}/add-to-order`, {
        method: 'POST',
        body: {
          customer_name: el('dialogCustomer').value,
          quantity: Number(el('dialogQty').value || 0),
          note: el('dialogNote').value,
        },
      });
      showToast('已加入訂單');
      await refreshAll();
      closeDialog();
      setView('orders');
    },
  });
};

window.openInventoryEditDialog = function(itemId) {
  const item = state.inventory.find((row) => row.id === itemId);
  if (!item) return;
  openDialog({
    title: `編輯庫存｜${item.product_name}`,
    html: `
      <label>商品<input id="dialogProduct" type="text" value="${escapeHtml(item.product_name)}"></label>
      <label>規格<input id="dialogSpec" type="text" value="${escapeHtml(item.spec || '')}"></label>
      <div class="inline-field">
        <label>數量<input id="dialogQty" type="number" min="0" value="${item.quantity}"></label>
        <label>單位<input id="dialogUnit" type="text" value="${escapeHtml(item.unit || '件')}"></label>
      </div>
      <label>客戶名稱<input id="dialogCustomer" type="text" value="${escapeHtml(item.customer_name || '')}"></label>
      <label>備註<textarea id="dialogNote" rows="3">${escapeHtml(item.note || '')}</textarea></label>
    `,
    submitText: '儲存',
    onSubmit: async () => {
      await api(`/api/inventory/${itemId}`, {
        method: 'PUT',
        body: {
          product_name: el('dialogProduct').value,
          spec: el('dialogSpec').value,
          quantity: Number(el('dialogQty').value || 0),
          unit: el('dialogUnit').value,
          customer_name: el('dialogCustomer').value,
          note: el('dialogNote').value,
        },
      });
      showToast('已更新庫存');
      await refreshAll();
      closeDialog();
    },
  });
};

window.openAssignSlotDialog = function(itemId) {
  const item = state.inventory.find((row) => row.id === itemId);
  if (!item) return;
  openDialog({
    title: `${item.slot_label ? '更換倉位' : '配置倉位'}｜${item.product_name}`,
    html: `
      <label>選擇格位
        <select id="dialogSlot">${buildSlotOptions(item.slot_id)}</select>
      </label>
      <div class="small-note">點確定後會即時寫入倉庫圖，首頁與今日異動同步更新。</div>
    `,
    submitText: '套用',
    onSubmit: async () => {
      await api(`/api/inventory/${itemId}/assign-slot`, {
        method: 'POST',
        body: { slot_id: Number(el('dialogSlot').value) },
      });
      showToast('已更新倉位');
      await refreshAll();
      closeDialog();
    },
  });
};

window.locateInventory = function(itemId) {
  const item = state.inventory.find((row) => row.id === itemId);
  if (!item || !item.slot_label) {
    showToast('此商品尚未錄入倉庫圖');
    return;
  }
  state.highlightSlotLabel = item.slot_label;
  setView('warehouse');
  renderWarehouse();
};

window.deleteInventory = async function(itemId) {
  if (!confirm('確定刪除此庫存？')) return;
  try {
    await api(`/api/inventory/${itemId}`, { method: 'DELETE' });
    showToast('已刪除庫存');
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.openOrderEditDialog = function(orderItemId) {
  const item = state.orders.flatMap((order) => order.items).find((row) => row.id === orderItemId);
  if (!item) return;
  openDialog({
    title: `修改訂單｜${item.product_name}`,
    html: `
      <label>數量<input id="dialogQty" type="number" min="1" value="${item.quantity}"></label>
      <label>備註<textarea id="dialogNote" rows="3">${escapeHtml(item.note || '')}</textarea></label>
    `,
    submitText: '更新',
    onSubmit: async () => {
      await api(`/api/orders/items/${orderItemId}`, {
        method: 'PUT',
        body: {
          quantity: Number(el('dialogQty').value || 0),
          note: el('dialogNote').value,
        },
      });
      showToast('已更新訂單');
      await refreshAll();
      closeDialog();
    },
  });
};

window.cancelOrderItem = async function(orderItemId) {
  if (!confirm('確定取消此訂單項目？庫存會回補。')) return;
  try {
    await api(`/api/orders/items/${orderItemId}`, { method: 'DELETE' });
    showToast('已取消訂單');
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.shipOrderItem = async function(orderItemId) {
  if (!confirm('確定執行出貨？')) return;
  try {
    await api(`/api/orders/items/${orderItemId}/ship`, { method: 'POST' });
    showToast('已完成出貨');
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.addOrderItemToMaster = async function(orderItemId) {
  try {
    await api(`/api/orders/items/${orderItemId}/to-master`, { method: 'POST' });
    showToast('已加入總單');
    await refreshAll();
    setView('master');
  } catch (error) {
    showToast(error.message);
  }
};

window.locateOrderItem = function(orderItemId) {
  const item = state.orders.flatMap((order) => order.items).find((row) => row.id === orderItemId);
  if (!item || !item.slot_label) {
    showToast('此商品尚未配置倉位');
    return;
  }
  state.highlightSlotLabel = item.slot_label;
  setView('warehouse');
  renderWarehouse();
};

window.deleteMasterItem = async function(itemId) {
  if (!confirm('確定刪除此總單項目？')) return;
  try {
    await api(`/api/master-orders/${itemId}`, { method: 'DELETE' });
    showToast('已刪除總單項目');
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.openSlotDialog = function(slotId) {
  const slot = state.slots.find((row) => row.id === slotId);
  if (!slot) return;
  openDialog({
    title: `倉位｜${slot.label}`,
    html: `
      <div class="small-note">目前商品：${escapeHtml(slot.item ? slot.item.product_name : '空位')}</div>
      <label>備註<textarea id="dialogNote" rows="3">${escapeHtml(slot.note || '')}</textarea></label>
      ${slot.item ? `<button type="button" class="btn btn-secondary" onclick="removeSlotAssignment(${slot.item.id})">移除此商品倉位</button>` : ''}
      ${slot.is_custom ? `<button type="button" class="btn btn-secondary" onclick="deleteSlot(${slot.id})">刪除此自訂格位</button>` : ''}
    `,
    submitText: '儲存備註',
    onSubmit: async () => {
      await api(`/api/warehouse/slots/${slot.id}`, {
        method: 'PUT',
        body: { note: el('dialogNote').value },
      });
      showToast('已更新格位');
      await refreshAll();
      closeDialog();
    },
  });
};

window.removeSlotAssignment = async function(itemId) {
  try {
    await api(`/api/inventory/${itemId}/unassign`, { method: 'POST' });
    showToast('已移除倉位');
    closeDialog();
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.deleteSlot = async function(slotId) {
  if (!confirm('確定刪除此格位？')) return;
  try {
    await api(`/api/warehouse/slots/${slotId}`, { method: 'DELETE' });
    showToast('已刪除格位');
    closeDialog();
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

window.deleteLog = async function(logId) {
  try {
    await api(`/api/activity/logs/${logId}`, { method: 'DELETE' });
    showToast('已刪除異動紀錄');
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
};

async function manualOrderDialog() {
  openDialog({
    title: '手動新增訂單',
    html: `
      <label>客戶名稱<input id="dialogCustomer" type="text"></label>
      <label>商品名稱<input id="dialogProduct" type="text"></label>
      <label>規格<input id="dialogSpec" type="text"></label>
      <div class="inline-field">
        <label>數量<input id="dialogQty" type="number" min="1" value="1"></label>
        <label>單位<input id="dialogUnit" type="text" value="件"></label>
      </div>
      <label>倉位（可空）<input id="dialogSlotLabel" type="text"></label>
      <label>備註<textarea id="dialogNote" rows="3"></textarea></label>
    `,
    submitText: '新增訂單',
    onSubmit: async () => {
      await api('/api/orders/manual', {
        method: 'POST',
        body: {
          customer_name: el('dialogCustomer').value,
          product_name: el('dialogProduct').value,
          spec: el('dialogSpec').value,
          quantity: Number(el('dialogQty').value || 0),
          unit: el('dialogUnit').value,
          slot_label: el('dialogSlotLabel').value,
          note: el('dialogNote').value,
        },
      });
      showToast('已建立訂單');
      await refreshAll();
      closeDialog();
    },
  });
}

async function addMasterDialog() {
  openDialog({
    title: '手動新增總單',
    html: `
      <label>商品名稱<input id="dialogProduct" type="text"></label>
      <label>規格<input id="dialogSpec" type="text"></label>
      <div class="inline-field">
        <label>數量<input id="dialogQty" type="number" min="1" value="1"></label>
        <label>單位<input id="dialogUnit" type="text" value="件"></label>
      </div>
      <label>備註<textarea id="dialogNote" rows="3"></textarea></label>
    `,
    submitText: '新增總單',
    onSubmit: async () => {
      await api('/api/master-orders', {
        method: 'POST',
        body: {
          product_name: el('dialogProduct').value,
          spec: el('dialogSpec').value,
          quantity: Number(el('dialogQty').value || 0),
          unit: el('dialogUnit').value,
          note: el('dialogNote').value,
        },
      });
      showToast('已新增總單');
      await refreshAll();
      closeDialog();
    },
  });
}

async function addSlotDialog() {
  openDialog({
    title: '新增自訂格位',
    html: `
      <div class="inline-field">
        <label>區域<input id="dialogZone" type="text" value="X"></label>
        <label>帶號<input id="dialogBand" type="number" min="1" value="1"></label>
      </div>
      <div class="inline-field">
        <label>排別
          <select id="dialogRow">
            <option value="front">front</option>
            <option value="back">back</option>
          </select>
        </label>
        <label>欄位<input id="dialogCol" type="number" min="1" value="1"></label>
      </div>
      <label>自訂標籤（可空）<input id="dialogLabel" type="text" placeholder="例如 X-1-F1"></label>
      <label>備註<textarea id="dialogNote" rows="3"></textarea></label>
    `,
    submitText: '新增格位',
    onSubmit: async () => {
      await api('/api/warehouse/slots', {
        method: 'POST',
        body: {
          zone: el('dialogZone').value,
          band: Number(el('dialogBand').value || 1),
          row: el('dialogRow').value,
          col_index: Number(el('dialogCol').value || 1),
          label: el('dialogLabel').value,
          note: el('dialogNote').value,
        },
      });
      showToast('已新增格位');
      await refreshAll();
      closeDialog();
    },
  });
}

async function loadReconcileReport() {
  const data = await api('/api/activity/reconcile');
  const rows = data.report.rows || [];
  const target = el('reconcileTable');
  if (!rows.length) {
    target.innerHTML = '<div style="padding:12px">目前沒有可顯示的對帳資料。</div>';
    return;
  }
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>商品</th>
          <th>規格</th>
          <th>訂單</th>
          <th>總單</th>
          <th>出貨</th>
          <th>庫存</th>
          <th>差異</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.product_name)}</td>
            <td>${escapeHtml(row.spec || '')}</td>
            <td>${row.order_qty}</td>
            <td>${row.master_qty}</td>
            <td>${row.shipped_qty}</td>
            <td>${row.inventory_qty}</td>
            <td>${row.has_difference ? '有' : '無'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function initCanvasSelection() {
  const canvas = el('ocrCanvas');
  const ctx = canvas.getContext('2d');
  let dragging = false;
  let startX = 0;
  let startY = 0;

  const redraw = () => {
    const image = state.ocr.image;
    if (!image) {
      canvas.width = 600;
      canvas.height = 360;
      ctx.fillStyle = '#f2ebe4';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#7a6a60';
      ctx.font = '18px sans-serif';
      ctx.fillText('請先從相簿選圖或拍照上傳', 28, 42);
      return;
    }

    const maxWidth = canvas.parentElement.clientWidth - 8;
    const ratio = image.naturalHeight / image.naturalWidth;
    canvas.width = maxWidth;
    canvas.height = maxWidth * ratio;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    if (state.ocr.selectedRect) {
      const r = state.ocr.selectedRect;
      ctx.strokeStyle = '#f08b49';
      ctx.lineWidth = 3;
      ctx.setLineDash([10, 6]);
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.fillStyle = 'rgba(240,139,73,.16)';
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.setLineDash([]);
    }
  };

  const getPoint = (event) => {
    const rect = canvas.getBoundingClientRect();
    const clientX = event.touches ? event.touches[0].clientX : event.clientX;
    const clientY = event.touches ? event.touches[0].clientY : event.clientY;
    return {
      x: clientX - rect.left,
      y: clientY - rect.top,
    };
  };

  const start = (event) => {
    if (!state.ocr.image) return;
    dragging = true;
    const p = getPoint(event);
    startX = p.x;
    startY = p.y;
    state.ocr.selectedRect = { x: startX, y: startY, w: 0, h: 0 };
    redraw();
  };

  const move = (event) => {
    if (!dragging || !state.ocr.image) return;
    const p = getPoint(event);
    state.ocr.selectedRect = {
      x: Math.min(startX, p.x),
      y: Math.min(startY, p.y),
      w: Math.abs(p.x - startX),
      h: Math.abs(p.y - startY),
    };
    redraw();
  };

  const end = () => {
    dragging = false;
    redraw();
  };

  ['mousedown', 'touchstart'].forEach((name) => canvas.addEventListener(name, start));
  ['mousemove', 'touchmove'].forEach((name) => canvas.addEventListener(name, move));
  ['mouseup', 'mouseleave', 'touchend'].forEach((name) => canvas.addEventListener(name, end));

  window.redrawOCRCanvas = redraw;
  redraw();
}

function loadImageFile(file) {
  if (!file) return;
  const image = new Image();
  image.onload = () => {
    state.ocr.image = image;
    state.ocr.naturalWidth = image.naturalWidth;
    state.ocr.naturalHeight = image.naturalHeight;
    state.ocr.selectedRect = null;
    state.ocr.imagePath = '';
    window.redrawOCRCanvas();
  };
  image.src = URL.createObjectURL(file);
}

function buildCropDataURL() {
  const image = state.ocr.image;
  if (!image) return null;
  const canvas = el('ocrCanvas');
  const rect = state.ocr.selectedRect;
  const sx = rect && rect.w > 10 && rect.h > 10 ? rect.x : 0;
  const sy = rect && rect.w > 10 && rect.h > 10 ? rect.y : 0;
  const sw = rect && rect.w > 10 && rect.h > 10 ? rect.w : canvas.width;
  const sh = rect && rect.w > 10 && rect.h > 10 ? rect.h : canvas.height;

  const scaleX = image.naturalWidth / canvas.width;
  const scaleY = image.naturalHeight / canvas.height;

  const off = document.createElement('canvas');
  off.width = sw * scaleX;
  off.height = sh * scaleY;
  const ctx = off.getContext('2d');
  ctx.drawImage(
    image,
    sx * scaleX,
    sy * scaleY,
    sw * scaleX,
    sh * scaleY,
    0,
    0,
    off.width,
    off.height
  );
  return off.toDataURL('image/png');
}

async function runOCR() {
  try {
    const croppedImage = buildCropDataURL();
    if (!croppedImage) throw new Error('請先選擇圖片');
    const data = await api('/api/inventory/ocr', {
      method: 'POST',
      body: { cropped_image: croppedImage },
    });
    state.ocr.imagePath = data.image_path || '';
    el('ocrText').value = data.text || '';
    el('ocrConfidence').value = Number(data.confidence || 0).toFixed(2);
    el('ocrCustomer').value = data.fields?.customer_name || '';
    el('ocrProduct').value = data.fields?.product_name || '';
    el('ocrSpec').value = data.fields?.spec || '';
    el('ocrQty').value = data.fields?.quantity || '';
    el('ocrUnit').value = data.fields?.unit || '件';
    el('ocrHints').innerHTML = (data.hints || []).map((hint) => `<div>• ${escapeHtml(hint)}</div>`).join('') || '<div>辨識完成，可直接手動修正後儲存。</div>';
    showToast(data.text ? 'OCR 完成' : '沒有抓到完整文字，請手動修正後儲存');
  } catch (error) {
    showToast(error.message);
  }
}

async function saveOCRToInventory() {
  try {
    await api('/api/inventory/create', {
      method: 'POST',
      body: {
        customer_name: el('ocrCustomer').value,
        product_name: el('ocrProduct').value,
        spec: el('ocrSpec').value,
        quantity: Number(el('ocrQty').value || 0),
        unit: el('ocrUnit').value,
        note: el('ocrNote').value,
        source_text: el('ocrText').value,
        image_path: state.ocr.imagePath,
        ocr_confidence: Number(el('ocrConfidence').value || 0),
      },
    });
    showToast('已儲存到庫存');
    ['ocrText', 'ocrCustomer', 'ocrProduct', 'ocrSpec', 'ocrQty', 'ocrNote'].forEach((id) => el(id).value = '');
    el('ocrUnit').value = '件';
    el('ocrConfidence').value = '';
    el('ocrHints').innerHTML = '';
    await refreshAll();
    setView('inventory');
  } catch (error) {
    showToast(error.message);
  }
}

function initSocket() {
  const socket = io();
  socket.on('connect', () => console.log('socket connected'));
  socket.on('data_changed', () => {
    if (state.user) queueRefresh();
  });
}

function initInstallPrompt() {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    state.installPrompt = event;
  });
  el('installBtn').addEventListener('click', async () => {
    if (!state.installPrompt) {
      showToast('目前請用瀏覽器選單安裝 App');
      return;
    }
    state.installPrompt.prompt();
    await state.installPrompt.userChoice;
    state.installPrompt = null;
  });
}

function bindEvents() {
  dialog.node = el('formDialog');
  dialog.title = el('dialogTitle');
  dialog.content = el('dialogContent');
  dialog.submit = el('dialogSubmitBtn');

  el('loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await login(el('loginUsername').value, el('loginPassword').value);
    } catch (error) {
      showToast(error.message);
    }
  });

  el('logoutBtn').addEventListener('click', async () => {
    try {
      await logout();
      showToast('已登出');
    } catch (error) {
      showToast(error.message);
    }
  });

  el('todayBtn').addEventListener('click', () => setView('today'));
  el('settingsBtn').addEventListener('click', () => setView('settings'));

  document.querySelectorAll('.nav-card').forEach((node) => {
    node.addEventListener('click', () => setView(node.dataset.view));
  });

  el('inventorySearch').addEventListener('input', () => loadInventory().catch((error) => showToast(error.message)));
  el('inventorySearchClear').addEventListener('click', () => {
    el('inventorySearch').value = '';
    loadInventory().catch((error) => showToast(error.message));
  });

  el('warehouseSearch').addEventListener('input', renderWarehouse);
  el('warehouseSearchClear').addEventListener('click', () => {
    el('warehouseSearch').value = '';
    renderWarehouse();
  });

  el('manualOrderBtn').addEventListener('click', manualOrderDialog);
  el('addMasterBtn').addEventListener('click', addMasterDialog);
  el('addSlotBtn').addEventListener('click', addSlotDialog);
  el('loadReconcileBtn').addEventListener('click', () => loadReconcileReport().catch((error) => showToast(error.message)));

  dialog.node.addEventListener('close', () => {
    dialog.onSubmit = null;
  });
  el('dialogForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!dialog.onSubmit) return dialog.node.close();
    try {
      await dialog.onSubmit();
    } catch (error) {
      showToast(error.message);
    }
  });

  el('albumInput').addEventListener('change', (event) => loadImageFile(event.target.files[0]));
  el('cameraInput').addEventListener('change', (event) => loadImageFile(event.target.files[0]));
  el('ocrRunBtn').addEventListener('click', runOCR);
  el('ocrResetBtn').addEventListener('click', () => {
    state.ocr.selectedRect = null;
    window.redrawOCRCanvas();
  });
  el('saveInventoryBtn').addEventListener('click', saveOCRToInventory);
}

async function boot() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => null);
  }
  setTodayLabel();
  bindEvents();
  initCanvasSelection();
  initSocket();
  initInstallPrompt();
  try {
    await loadMe();
    if (state.user) {
      await refreshAll();
      setView('home');
    }
  } catch (error) {
    showToast(error.message);
  }
}

window.addEventListener('DOMContentLoaded', boot);
