
const App = {
  state: {
    module: window.APP_CONFIG?.module || null,
    inventory: window.APP_CONFIG?.inventory || [],
    orders: window.APP_CONFIG?.orders || [],
    masters: window.APP_CONFIG?.masters || [],
    shippingRecords: window.APP_CONFIG?.shippingRecords || [],
    customers: window.APP_CONFIG?.customers || [],
    warehouseA: window.APP_CONFIG?.warehouseA || [],
    warehouseB: window.APP_CONFIG?.warehouseB || [],
    notifications: window.APP_CONFIG?.notifications || [],
    logs: window.APP_CONFIG?.logs || [],
    discrepancies: window.APP_CONFIG?.discrepancies || [],
    summary: window.APP_CONFIG?.summary || {},
    backups: window.APP_CONFIG?.backups || [],
    settings: window.APP_CONFIG?.settings || [],
    activeZone: 'A',
    editMode: true,
    lastNotifId: 0,
    ocrCache: {},
    loaded: false,
  },

  initLogin() {
    const user = localStorage.getItem('username') || '';
    const pass = localStorage.getItem('password') || '';
    if (user) document.getElementById('username').value = user;
    if (pass) document.getElementById('password').value = pass;
    const remember = localStorage.getItem('remember') !== '0';
    const saveCreds = localStorage.getItem('saveCreds') === '1';
    document.getElementById('remember').checked = remember;
    document.getElementById('saveCreds').checked = saveCreds;
    if (user && pass) {
      App.login(true);
    }
  },

  toast(title, message='', type='good', timeout=2400) {
    const wrap = document.getElementById('toastContainer');
    if (!wrap) return;
    const node = document.createElement('div');
    node.className = `toast ${type}`;
    node.innerHTML = `<strong>${title}</strong>${message ? `<div>${message}</div>` : ''}`;
    wrap.appendChild(node);
    setTimeout(() => {
      node.style.opacity = '0';
      node.style.transform = 'translateY(-8px)';
      node.style.transition = 'all .2s ease';
      setTimeout(() => node.remove(), 240);
    }, timeout);
  },

  openModal(title, html) {
    document.getElementById('modalTitle').innerText = title;
    document.getElementById('modalContent').innerHTML = html;
    document.getElementById('modalBackdrop').classList.add('show');
  },

  closeModal() {
    document.getElementById('modalBackdrop').classList.remove('show');
  },

  async fetchJSON(url, options={}) {
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json', ...(options.headers || {}) },
      ...options
    });
    const txt = await res.text();
    let data;
    try { data = JSON.parse(txt); }
    catch (e) {
      console.error('Non-JSON response:', txt);
      throw new Error('伺服器回傳格式錯誤');
    }
    if (!res.ok || data.success === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  },

  async login(auto=false) {
    const username = (document.getElementById('username').value || '').trim();
    const password = (document.getElementById('password').value || '').trim();
    const remember = !!document.getElementById('remember').checked;
    const saveCreds = !!document.getElementById('saveCreds').checked;
    if (!username || !password) {
      if (!auto) App.toast('請輸入帳號與密碼', '', 'warn');
      return;
    }
    try {
      const data = await App.fetchJSON('/api/login', {
        method: 'POST',
        body: JSON.stringify({ username, password, remember })
      });
      localStorage.setItem('username', username);
      localStorage.setItem('remember', remember ? '1' : '0');
      localStorage.setItem('saveCreds', saveCreds ? '1' : '0');
      if (saveCreds) localStorage.setItem('password', password);
      else localStorage.removeItem('password');
      App.toast('登入成功', username, 'good');
      window.location.href = '/';
    } catch (e) {
      if (!auto) App.toast('登入失敗', e.message, 'bad');
    }
  },

  async changePassword() {
    try {
      await App.fetchJSON('/api/change_password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: document.getElementById('oldPassword').value.trim(),
          new_password: document.getElementById('newPassword').value.trim(),
          confirm_password: document.getElementById('confirmPassword').value.trim(),
        })
      });
      App.toast('密碼已修改', '', 'good');
      ['oldPassword','newPassword','confirmPassword'].forEach(id => document.getElementById(id).value = '');
    } catch (e) {
      App.toast('修改失敗', e.message, 'bad');
    }
  },

  pickFile(module) {
    const input = document.getElementById(`${module}File`);
    if (input) input.click();
  },

  triggerCamera(module) {
    const input = document.getElementById(`${module}File`);
    if (input) input.click();
  },

  async handleUpload(module, input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const confidenceNode = document.getElementById(`${module}Confidence`);
    const textNode = document.getElementById(`${module}OcrText`);
    if (confidenceNode) confidenceNode.innerText = '辨識中...';
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('blue_only', '1');
      const res = await fetch('/api/upload_ocr', { method: 'POST', body: formData });
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch (e) { throw new Error('伺服器回傳格式錯誤'); }
      if (!res.ok || data.success === false) throw new Error(data.error || 'OCR失敗');
      if (textNode) textNode.value = data.text || '';
      if (confidenceNode) confidenceNode.innerText = `${data.confidence || 0}%`;
      if (data.warning) App.toast('提醒', data.warning, 'warn');
      if (data.duplicate) App.toast('重複圖片', '仍已輸出辨識結果', 'good');
      App.state.ocrCache[module] = data.text || '';
      if (data.customer_guess && document.getElementById(`${module}Customer`)) {
        document.getElementById(`${module}Customer`).value = data.customer_guess;
      }
      App.renderPreview(module, data);
      App.toast('OCR 完成', `${(data.items || []).length} 筆`, 'good');
    } catch (e) {
      if (confidenceNode) confidenceNode.innerText = '--';
      App.toast('OCR 失敗', e.message, 'bad');
    } finally {
      input.value = '';
    }
  },


  renderCustomerChips(module) {
    const el = document.getElementById(`${module}CustomerChips`);
    if (!el) return;
    const groups = {
      '北區': ['北區','north','N'],
      '中區': ['中區','central','C'],
      '南區': ['南區','south','S'],
      '其他': []
    };
    const customers = App.state.customers || [];
    const byRegion = { '北區': [], '中區': [], '南區': [], '其他': [] };
    customers.forEach(c => {
      const region = (c.region || '').trim();
      if (region.includes('北')) byRegion['北區'].push(c);
      else if (region.includes('中')) byRegion['中區'].push(c);
      else if (region.includes('南')) byRegion['南區'].push(c);
      else byRegion['其他'].push(c);
    });
    el.innerHTML = Object.keys(byRegion).map(region => `
      <div class="card soft" style="padding:12px;border-radius:18px">
        <div class="toolbar">
          <strong>${region}</strong>
          <span class="small muted">可拖曳分類</span>
        </div>
        <div class="chips" data-region="${region}" ondragover="event.preventDefault()" ondrop="App.dropCustomerRegion(event, '${region}')">
          ${byRegion[region].map(c => `
            <span class="chip" draggable="true" ondragstart="App.dragCustomer(event, ${JSON.stringify(c.customer_name || '')}, ${JSON.stringify(c.region || '')})" onclick="App.chooseCustomer('${module}', ${JSON.stringify(c.customer_name || '')})">
              ${c.customer_name || ''}
            </span>
          `).join('')}
        </div>
      </div>
    `).join('');
  },

  dragCustomer(ev, name, region) {
    ev.dataTransfer.setData('text/plain', JSON.stringify({ name, region }));
  },

  async dropCustomerRegion(ev, region) {
    ev.preventDefault();
    try {
      const data = JSON.parse(ev.dataTransfer.getData('text/plain'));
      if (!data.name) return;
      await App.fetchJSON('/api/customers/update', {
        method: 'POST',
        body: JSON.stringify({ customer_name: data.name, region })
      });
      App.toast('已分類', `${data.name} → ${region}`, 'good');
      await App.loadCustomers();
      if (['orders','master_orders','shipping'].includes(App.state.module)) App.renderCustomerChips(App.state.module);
    } catch (e) {
      App.toast('分類失敗', e.message, 'bad');
    }
  },

  renderPreview(module, data) {
    const el = document.getElementById(`${module}Preview`);
    if (!el) return;
    const items = data.items || [];
    el.innerHTML = items.map((item, idx) => `
      <div class="list-item">
        <div class="meta">
          <div class="title">${item.product || item.product_name || ''}</div>
          <div class="desc">${item.quantity || 1}</div>
        </div>
        <div class="small">#${idx+1}</div>
      </div>
    `).join('') || '<div class="note-box">尚未辨識到內容</div>';
  },

  searchCustomers(q, module) {
    const box = document.getElementById(`${module}CustomerSug`);
    const list = App.state.customers || [];
    if (!box) return;
    const query = (q || '').trim();
    if (!query) {
      box.style.display = 'none';
      box.innerHTML = '';
      return;
    }
    const matches = list
      .map(x => x.customer_name || '')
      .filter(name => name.includes(query) || query.split('').every(ch => name.includes(ch)))
      .slice(0, 12);
    box.innerHTML = matches.map(name => `<div class="suggestion" onclick="App.chooseCustomer('${module}', ${JSON.stringify(name)})">${name}</div>`).join('');
    box.style.display = matches.length ? 'block' : 'none';
  },

  chooseCustomer(module, name) {
    const input = document.getElementById(`${module}Customer`);
    const box = document.getElementById(`${module}CustomerSug`);
    if (input) input.value = name;
    if (box) { box.style.display = 'none'; box.innerHTML = ''; }
  },

  async submitModule(module) {
    try {
      const customer = (document.getElementById(`${module}Customer`)?.value || '').trim();
      const ocr = (document.getElementById(`${module}OcrText`)?.value || '').trim();
      const items = App.parseOcrLines(ocr);
      const payload = { customer, items, note: '' };
      let url = '';
      if (module === 'inventory') {
        url = '/api/inventory';
        payload.items = items;
        // inventory direct products, no customer categories
      } else if (module === 'orders') {
        url = '/api/orders';
      } else if (module === 'master_orders') {
        url = '/api/master_orders';
      } else if (module === 'shipping') {
        url = '/api/ship';
      }
      if (!url) return;
      if (!items.length && module !== 'shipping') {
        App.toast('請先輸入內容', '', 'warn');
        return;
      }
      if (module === 'shipping') {
        if (!confirm('出貨前再次確認？')) return;
      }
      await App.fetchJSON(url, {
        method: 'POST',
        body: JSON.stringify({ customer, items, note: '' })
      });
      App.toast('已送出', module === 'shipping' ? '完成出貨' : '資料已建立', 'good');
      // Learn corrections after manual edits
      App.learnCorrection(module);
      setTimeout(() => location.reload(), 700);
    } catch (e) {
      App.toast('送出失敗', e.message, 'bad');
    }
  },

  parseOcrLines(text) {
    const lines = (text || '').split('\n').map(x => x.trim()).filter(Boolean);
    return lines.map(line => {
      let p = line;
      let qty = 1;
      const m = line.match(/(.+?)[=\*xX](\d+)$/);
      if (m) { p = m[1]; qty = parseInt(m[2], 10) || 1; }
      return { product: p, quantity: qty };
    });
  },

  async learnCorrection(module) {
    const original = App.state.ocrCache[module] || '';
    const edited = (document.getElementById(`${module}OcrText`)?.value || '').trim();
    if (!original || !edited || original === edited) return;
    const origLines = original.split('\n').filter(Boolean);
    const editLines = edited.split('\n').filter(Boolean);
    // simple line-by-line learning
    for (let i = 0; i < Math.min(origLines.length, editLines.length); i++) {
      if (origLines[i] !== editLines[i]) {
        try {
          await App.fetchJSON('/api/save_correction', {
            method: 'POST',
            body: JSON.stringify({ wrong_text: origLines[i], correct_text: editLines[i] })
          });
        } catch (e) {}
      }
    }
  },

  filterInventory(q) {
    const rows = document.querySelectorAll('#inventoryTable tr');
    const query = (q || '').trim();
    rows.forEach(row => {
      const t = row.innerText;
      row.style.display = !query || t.includes(query) ? '' : 'none';
    });
  },

  filterShipDays(days) {
    App.loadShippingRecords(days);
  },

  async loadShippingRecords(days='') {
    try {
      const url = days ? `/api/shipping_records?days=${encodeURIComponent(days)}` : '/api/shipping_records';
      const data = await App.fetchJSON(url);
      const tbody = document.getElementById('shippingRecordsTable');
      if (!tbody) return;
      tbody.innerHTML = data.records.map(r => `
        <tr>
          <td>${r.customer || ''}</td>
          <td>${r.product || ''}</td>
          <td>${r.qty || 0}</td>
          <td>${r.operator || ''}</td>
          <td>${r.shipped_at || ''}</td>
          <td>${r.detail || ''}</td>
        </tr>
      `).join('') || '<tr><td colspan="6" class="center-note">尚無出貨資料</td></tr>';
    } catch (e) {}
  },

  async loadCustomers() {
    try {
      const data = await App.fetchJSON('/api/customers');
      App.state.customers = data.items || [];
      const tbody = document.getElementById('customersTable');
      if (!tbody) return;
      tbody.innerHTML = data.items.map(c => `
        <tr>
          <td><input class="input" data-customer-name="${c.customer_name}" value="${c.customer_name || ''}" disabled></td>
          <td><input class="input" id="phone-${encodeURIComponent(c.customer_name)}" value="${c.phone || ''}"></td>
          <td><input class="input" id="address-${encodeURIComponent(c.customer_name)}" value="${c.address || ''}"></td>
          <td><input class="input" id="special-${encodeURIComponent(c.customer_name)}" value="${c.special_requests || ''}"></td>
          <td><input class="input" id="region-${encodeURIComponent(c.customer_name)}" value="${c.region || ''}"></td>
          <td><button class="primary" onclick="App.saveCustomer(${JSON.stringify(c.customer_name)})">儲存</button></td>
        </tr>
      `).join('') || '<tr><td colspan="6" class="center-note">尚無客戶資料</td></tr>';
      if (['orders','master_orders','shipping'].includes(App.state.module)) App.renderCustomerChips(App.state.module);
    } catch (e) {}
  },

  async saveCustomer(name) {
    try {
      const enc = encodeURIComponent(name);
      await App.fetchJSON('/api/customers/update', {
        method: 'POST',
        body: JSON.stringify({
          customer_name: name,
          phone: document.getElementById(`phone-${enc}`)?.value || '',
          address: document.getElementById(`address-${enc}`)?.value || '',
          special_requests: document.getElementById(`special-${enc}`)?.value || '',
          region: document.getElementById(`region-${enc}`)?.value || '',
        })
      });
      App.toast('已儲存', name, 'good');
      App.reloadCustomers();
    } catch (e) {
      App.toast('儲存失敗', e.message, 'bad');
    }
  },

  async reloadCustomers() {
    await App.loadCustomers();
  },

  renderInventory() {
    const tbody = document.getElementById('inventoryTable');
    if (!tbody) return;
    const rows = (window.APP_CONFIG.rawInventory || App.state.inventory || []).length ? (window.APP_CONFIG.rawInventory || App.state.inventory) : App.state.inventory;
    const items = App.state.inventory || [];
    tbody.innerHTML = items.map(item => {
      const isRed = item.is_unplaced || !item.locations || !item.locations.length;
      const loc = (item.locations || []).join(', ');
      const cust = (item.customers || []).join(', ');
      return `
        <tr class="${isRed ? 'red' : ''}">
          <td>${item.product || ''}</td>
          <td>${item.quantity || 0}</td>
          <td class="${isRed ? 'red' : ''}">${loc || '未上架'}</td>
          <td>${cust || ''}</td>
          <td>${isRed ? '<span class="red">尚未錄入倉庫圖</span>' : '<span class="green">已上架</span>'}</td>
        </tr>
      `;
    }).join('') || '<tr><td colspan="5" class="center-note">尚無庫存資料</td></tr>';
    App.filterInventory(document.getElementById('inventorySearch')?.value || '');
  },

  renderOrders() {
    const tbody = document.getElementById('ordersTable');
    if (!tbody) return;
    tbody.innerHTML = (App.state.orders || []).map(o => `
      <tr>
        <td>${o.customer || ''}</td>
        <td>${o.product || ''}</td>
        <td>${o.qty || 0}</td>
        <td>${o.status || ''}</td>
        <td>${o.created_at || ''}</td>
      </tr>
    `).join('') || '<tr><td colspan="5" class="center-note">尚無訂單資料</td></tr>';
  },

  renderMasters() {
    const tbody = document.getElementById('mastersTable');
    if (!tbody) return;
    tbody.innerHTML = (App.state.masters || []).map(m => `
      <tr>
        <td>${m.product || ''}</td>
        <td>${m.qty || 0}</td>
        <td>${m.updated_at || ''}</td>
      </tr>
    `).join('') || '<tr><td colspan="3" class="center-note">尚無總單資料</td></tr>';
  },

  renderSummaryCards() {
    const s = App.state.summary || {};
    const el = document.getElementById('todayStats');
    if (!el) return;
    el.innerHTML = `
      <div class="stat"><div class="label">今日新增</div><div class="value">${s.order_count || 0}</div></div>
      <div class="stat"><div class="label">今日出貨</div><div class="value">${s.today_ship_count || 0}</div></div>
      <div class="stat"><div class="label">未上架商品</div><div class="value">${s.unplaced_count || 0}</div></div>
    `;
  },

  renderNotifications() {
    const list = document.getElementById('notificationsList');
    const logsTable = document.getElementById('logsTable');
    const reconcileList = document.getElementById('reconcileList');
    const reconcileList2 = document.getElementById('reconcileList2');
    const unplacedList = document.getElementById('unplacedList');
    const shipSummary = document.getElementById('shipSummary');
    const settingsList = document.getElementById('settingsList');

    if (list) {
      list.innerHTML = (App.state.notifications || []).map(n => `
        <div class="list-item clickable" onclick="App.markNotificationsRead(); App.toast('${n.title || ''}','${n.message || ''}','good')">
          <div class="meta">
            <div class="title">${n.title || ''}</div>
            <div class="desc">${n.created_at || ''} ｜ ${n.message || ''}</div>
          </div>
          <div class="small">${n.category || ''}</div>
        </div>
      `).join('') || '<div class="center-note">尚無通知</div>';
    }

    if (logsTable) {
      logsTable.innerHTML = (App.state.logs || []).map(l => `
        <tr>
          <td>${l.username || ''}</td>
          <td>${l.created_at || ''}</td>
          <td>${l.action || ''}</td>
          <td>${[l.target_type || '', l.target_name || ''].filter(Boolean).join(' / ')}</td>
          <td>${l.detail || ''}</td>
        </tr>
      `).join('') || '<tr><td colspan="5" class="center-note">尚無操作歷史</td></tr>';
    }

    const renderReconcile = target => {
      if (!target) return;
      target.innerHTML = (App.state.discrepancies || []).map(d => `
        <div class="list-item">
          <div class="meta">
            <div class="title">${d.customer || ''}｜${d.product || ''}</div>
            <div class="desc">總單:${d.master_qty} / 訂單:${d.order_qty} / 出貨:${d.ship_qty} / 庫存:${d.inventory_qty}</div>
          </div>
          <div class="small red">差異</div>
        </div>
      `).join('') || '<div class="center-note">沒有差異</div>';
    };
    renderReconcile(reconcileList);
    renderReconcile(reconcileList2);

    if (unplacedList) {
      unplacedList.innerHTML = (App.state.summary?.unplaced_items || []).map(i => `
        <div class="list-item">
          <div class="meta">
            <div class="title red">${i.product || ''}</div>
            <div class="desc">數量 ${i.quantity || 0}</div>
          </div>
          <div class="small red">未上架</div>
        </div>
      `).join('') || '<div class="center-note">全部已上架</div>';
    }

    if (shipSummary) {
      shipSummary.innerHTML = (App.state.orders || []).slice(0,10).map(o => `
        <div class="list-item">
          <div class="meta">
            <div class="title">${o.customer || ''}</div>
            <div class="desc">${o.product || ''} × ${o.qty || 0}</div>
          </div>
          <div class="small">${o.status || ''}</div>
        </div>
      `).join('') || '<div class="center-note">尚無需出貨的項目</div>';
    }

    if (settingsList) {
      settingsList.innerHTML = (App.state.settings || []).map(s => `
        <div class="list-item">
          <div class="meta">
            <div class="title">${s.key || ''}</div>
            <div class="desc">${s.value || ''}</div>
          </div>
        </div>
      `).join('') || '<div class="center-note">尚無設定</div>';
    }
  },

  showZone(zone) {
    App.state.activeZone = zone;
    document.getElementById('zoneA')?.classList.toggle('active', zone === 'A');
    document.getElementById('zoneB')?.classList.toggle('active', zone === 'B');
    document.getElementById('zoneBtnA')?.classList.toggle('active', zone === 'A');
    document.getElementById('zoneBtnB')?.classList.toggle('active', zone === 'B');
  },

  toggleWarehouseView() {
    App.state.editMode = !App.state.editMode;
    App.toast('模式切換', App.state.editMode ? '編輯模式' : '檢視模式', 'good');
  },

  slotLabel(slot) {
    if (!slot) return '<span class="slot-label">空格</span>';
    return `
      <div class="slot-customer">${slot.customer_name || ''}</div>
      <div class="slot-product">${slot.product || ''} ${slot.quantity ? '×' + slot.quantity : ''}</div>
      <div class="slot-label">${slot.note || ''}</div>
    `;
  },

  renderWarehouse(zone, bands) {
    const root = document.getElementById(zone === 'A' ? 'zoneA' : 'zoneB');
    if (!root) return;
    const html = `
      <div class="zone-shell">
        <div class="zone-label">${zone}</div>
        <div class="band-list">
          ${bands.map(b => `
            <div class="band">
              <div class="band-num">${b.band_no}</div>
              <div class="band-body">
                <div class="row-label">前排</div>
                <div class="cell-row">
                  ${b.front.map((slot, idx) => App.renderSlot(zone, b.band_no, 'front', idx+1, slot)).join('')}
                </div>
                <div class="row-label">後排</div>
                <div class="cell-row">
                  ${b.back.map((slot, idx) => App.renderSlot(zone, b.band_no, 'back', idx+1, slot)).join('')}
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
    root.innerHTML = html;
  },

  renderSlot(zone, bandNo, rowLabel, cellNo, slot) {
    const empty = !slot;
    const classes = ['slot', empty ? 'empty' : '', slot && !slot.product ? 'unplaced' : ''].join(' ').trim();
    const slotKey = `${zone}-${bandNo}-${rowLabel}-${cellNo}`;
    return `
      <div class="${classes}" data-zone="${zone}" data-band="${bandNo}" data-row="${rowLabel}" data-cell="${cellNo}"
           draggable="true"
           ondragstart="App.dragStart(event)"
           ondragover="App.dragOver(event)"
           ondrop="App.dropCell(event)"
           onclick="App.openCellEditor('${zone}', ${bandNo}, '${rowLabel}', ${cellNo})">
        <div class="slot-key">${slotKey}</div>
        ${App.slotLabel(slot)}
      </div>
    `;
  },

  dragStart(ev) {
    const el = ev.currentTarget;
    ev.dataTransfer.setData('text/plain', JSON.stringify({
      zone: el.dataset.zone,
      band: el.dataset.band,
      row: el.dataset.row,
      cell: el.dataset.cell
    }));
  },

  dragOver(ev) {
    ev.preventDefault();
    ev.currentTarget.classList.add('dragover');
  },

  async dropCell(ev) {
    ev.preventDefault();
    const target = ev.currentTarget;
    target.classList.remove('dragover');
    try {
      const source = JSON.parse(ev.dataTransfer.getData('text/plain'));
      const srcData = await App.getSlot(source.zone, source.band, source.row, source.cell);
      const tgtData = await App.getSlot(target.dataset.zone, target.dataset.band, target.dataset.row, target.dataset.cell);
      await App.saveSlot(target.dataset.zone, target.dataset.band, target.dataset.row, target.dataset.cell, srcData);
      await App.saveSlot(source.zone, source.band, source.row, source.cell, tgtData);
      App.toast('已移動', '格位拖曳完成', 'good');
      await App.loadWarehouse();
    } catch (e) {
      App.toast('拖曳失敗', e.message, 'bad');
    }
  },

  async getSlot(zone, band, row, cell) {
    const data = await App.fetchJSON(`/api/warehouse?zone=${zone}`);
    const bands = data.bands || [];
    const bandObj = bands.find(x => String(x.band_no) === String(band));
    const arr = bandObj ? (row === 'front' ? bandObj.front : bandObj.back) : [];
    return arr[Number(cell)-1] || null;
  },

  async saveSlot(zone, band, row, cell, slot) {
    const payload = {
      zone, band_no: Number(band), row_label: row, cell_no: Number(cell),
      customer_name: slot?.customer_name || '',
      product: slot?.product || '',
      quantity: slot?.quantity || 0,
      note: slot?.note || '',
    };
    await App.fetchJSON('/api/warehouse', { method: 'POST', body: JSON.stringify(payload) });
  },

  async openCellEditor(zone, band, row, cell) {
    try {
      const info = await App.fetchJSON(`/api/warehouse?zone=${zone}`);
      const bands = info.bands || [];
      const bandObj = bands.find(x => String(x.band_no) === String(band));
      const slot = bandObj ? (row === 'front' ? bandObj.front[cell-1] : bandObj.back[cell-1]) : null;
      const suggestions = await App.fetchJSON('/api/warehouse/slots?zone=' + zone + '&band_no=' + band + '&row_label=' + row + '&cell_no=' + cell);
      const allNames = (App.state.customers || []).map(c => c.customer_name).filter(Boolean);
      App.openModal(`編輯格位 ${zone}-${band}-${row}-${cell}`, `
        <div class="modal-grid">
          <div>
            <div class="label">客戶名稱（輸入關鍵字直接跳出完整名稱）</div>
            <div class="autocomplete">
              <input class="input" id="slotCustomer" value="${slot?.customer_name || ''}" oninput="App.searchSlotCustomers(this.value)">
              <div id="slotCustomerSug" class="suggestions"></div>
            </div>
            <div style="height:10px"></div>
            <div class="label">商品</div>
            <input class="input" id="slotProduct" value="${slot?.product || ''}" placeholder="可搜尋：113">
            <div style="height:10px"></div>
            <div class="label">數量</div>
            <input class="input" id="slotQty" type="number" value="${slot?.quantity || 0}">
            <div style="height:10px"></div>
            <div class="label">備註</div>
            <textarea id="slotNote">${slot?.note || ''}</textarea>
          </div>
          <div>
            <div class="label">已錄入下拉選項（可直接添加）</div>
            <select id="slotPreset" onchange="App.applyPreset(this.value)">
              <option value="">--選擇已錄入項目--</option>
              ${(suggestions.suggestions || []).map(s => `<option value="${s.product}|${s.customer_name}|${s.quantity}">${s.product} ｜ ${s.customer_name || ''} ｜ ${s.quantity || 0}</option>`).join('')}
            </select>
            <div style="height:10px"></div>
            <div class="label">搜尋商品</div>
            <input class="input" id="slotSearch" placeholder="輸入 113 即可篩選" oninput="App.filterSlotSuggestions(this.value)">
            <div style="height:10px"></div>
            <div id="slotSuggestionList" class="list" style="max-height:320px;overflow:auto">
              ${(suggestions.suggestions || []).map(s => `
                <div class="list-item clickable" onclick="App.fillSlotFromSuggestion(${JSON.stringify(s)})">
                  <div class="meta">
                    <div class="title">${s.product || ''}</div>
                    <div class="desc">${s.customer_name || ''} ｜ ${s.quantity || 0}</div>
                  </div>
                  <div class="small">點選添加</div>
                </div>
              `).join('')}
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="ghost" onclick="App.clearSlot('${zone}', ${band}, '${row}', ${cell})">清空</button>
          <button class="primary" onclick="App.saveOpenSlot('${zone}', ${band}, '${row}', ${cell})">儲存</button>
        </div>
      `);
      App.state.currentCell = { zone, band, row, cell };
    } catch (e) {
      App.toast('開啟格位失敗', e.message, 'bad');
    }
  },

  searchSlotCustomers(q) {
    const box = document.getElementById('slotCustomerSug');
    const query = (q || '').trim();
    if (!box) return;
    const matches = (App.state.customers || []).map(c => c.customer_name || '').filter(name => name.includes(query) || query.split('').every(ch => name.includes(ch))).slice(0, 12);
    box.innerHTML = matches.map(name => `<div class="suggestion" onclick="document.getElementById('slotCustomer').value=${JSON.stringify(name)};document.getElementById('slotCustomerSug').style.display='none'">${name}</div>`).join('');
    box.style.display = matches.length ? 'block' : 'none';
  },

  filterSlotSuggestions(q) {
    const query = (q || '').trim();
    document.querySelectorAll('#slotSuggestionList .list-item').forEach(el => {
      el.style.display = !query || el.innerText.includes(query) ? '' : 'none';
    });
  },

  fillSlotFromSuggestion(s) {
    document.getElementById('slotProduct').value = s.product || '';
    document.getElementById('slotCustomer').value = s.customer_name || '';
    document.getElementById('slotQty').value = s.quantity || 0;
  },

  applyPreset(val) {
    if (!val) return;
    const [product, customer, qty] = val.split('|');
    document.getElementById('slotProduct').value = product || '';
    document.getElementById('slotCustomer').value = customer || '';
    document.getElementById('slotQty').value = qty || 0;
  },

  async saveOpenSlot(zone, band, row, cell) {
    try {
      await App.fetchJSON('/api/warehouse', {
        method: 'POST',
        body: JSON.stringify({
          zone,
          band_no: band,
          row_label: row,
          cell_no: cell,
          customer_name: document.getElementById('slotCustomer').value.trim(),
          product: document.getElementById('slotProduct').value.trim(),
          quantity: Number(document.getElementById('slotQty').value || 0),
          note: document.getElementById('slotNote').value.trim()
        })
      });
      App.toast('已儲存', '倉庫格位更新完成', 'good');
      App.closeModal();
      await App.loadWarehouse();
    } catch (e) {
      App.toast('儲存失敗', e.message, 'bad');
    }
  },

  async clearSlot(zone, band, row, cell) {
    try {
      document.getElementById('slotCustomer').value = '';
      document.getElementById('slotProduct').value = '';
      document.getElementById('slotQty').value = 0;
      document.getElementById('slotNote').value = '';
      await App.saveOpenSlot(zone, band, row, cell);
    } catch (e) {
      App.toast('清空失敗', e.message, 'bad');
    }
  },

  async loadWarehouse() {
    if (!document.getElementById('zoneA')) return;
    try {
      const a = await App.fetchJSON('/api/warehouse?zone=A');
      const b = await App.fetchJSON('/api/warehouse?zone=B');
      App.state.warehouseA = a.bands || [];
      App.state.warehouseB = b.bands || [];
      App.renderWarehouse('A', App.state.warehouseA);
      App.renderWarehouse('B', App.state.warehouseB);
      App.showZone(App.state.activeZone || 'A');
      App.renderUnplacedList();
    } catch (e) {
      console.error(e);
    }
  },

  renderUnplacedList() {
    const el = document.getElementById('unplacedList');
    if (!el) return;
    const items = (App.state.summary?.unplaced_items || []);
    el.innerHTML = items.map(i => `
      <div class="list-item">
        <div class="meta">
          <div class="title red">${i.product || ''}</div>
          <div class="desc">${(i.locations || []).join(', ') || '未上架'} ｜ ${i.quantity || 0}</div>
        </div>
        <div class="small red">紅字</div>
      </div>
    `).join('') || '<div class="center-note">沒有未上架商品</div>';
  },

  async poll() {
    try {
      const s = await App.fetchJSON('/api/summary');
      App.state.summary = s.summary || {};
      const badge = document.getElementById('todayBadge');
      if (badge) badge.innerText = App.state.summary.unread_notifications || 0;
      const notes = await App.fetchJSON('/api/notifications/latest?since_id=' + App.state.lastNotifId);
      const newItems = notes.items || [];
      if (newItems.length) {
        App.state.lastNotifId = newItems[newItems.length-1].id || App.state.lastNotifId;
        newItems.forEach(n => App.toast(n.title || '通知', n.message || '', 'good'));
      }
      if (App.state.module === 'today') {
        await App.loadToday();
      }
      if (App.state.module === 'warehouse') await App.loadWarehouse();
      if (App.state.module === 'inventory') { await App.loadInventory(); }
      if (App.state.module === 'customers') await App.loadCustomers();
    } catch (e) {}
  },

  async markNotificationsRead() {
    try {
      await App.fetchJSON('/api/notifications/read', { method:'POST', body: JSON.stringify({}) });
      const badge = document.getElementById('todayBadge');
      if (badge) badge.innerText = '0';
      await App.loadToday();
    } catch (e) {}
  },

  async loadToday() {
    try {
      const data = await App.fetchJSON('/api/today_changes');
      App.state.notifications = data.notifications || [];
      App.state.logs = data.logs || [];
      App.state.discrepancies = data.discrepancies || [];
      App.state.summary = data.summary || {};
      App.renderSummaryCards();
      App.renderNotifications();
      App.renderUnplacedList();
    } catch (e) {}
  },

  async loadInventory() {
    try {
      const data = await App.fetchJSON('/api/inventory');
      App.state.inventory = data.items || [];
      App.renderInventory();
    } catch (e) {}
  },

  initModule() {
    if (App.state.module === 'inventory') App.renderInventory();
    if (App.state.module === 'orders') App.renderOrders();
    if (App.state.module === 'master_orders') App.renderMasters();
    if (App.state.module === 'shipping_records') App.loadShippingRecords();
    if (App.state.module === 'customers') App.loadCustomers();
    if (['orders','master_orders','shipping'].includes(App.state.module)) App.renderCustomerChips(App.state.module);
    if (App.state.module === 'warehouse') App.loadWarehouse();
    if (App.state.module === 'today') App.loadToday();
    if (App.state.module === 'settings') App.renderNotifications();
    if (App.state.module === 'reconcile') App.renderNotifications();
    App.renderSummaryCards();
    App.renderNotifications();
    App.renderUnplacedList();
    App.applyNotificationCount();
  },

  applyNotificationCount() {
    const badge = document.getElementById('todayBadge');
    if (badge) badge.innerText = App.state.summary?.unread_notifications || window.APP_CONFIG.unreadCount || 0;
  },

  attachCameraButton() {
    const module = App.state.module;
    if (!['inventory','orders','master_orders','shipping'].includes(module)) return;
    if (document.getElementById('floatingCameraBtn')) return;
    const btn = document.createElement('button');
    btn.id = 'floatingCameraBtn';
    btn.className = 'icon-btn camera';
    btn.innerHTML = '📷';
    btn.title = '拍照 / 上傳';
    btn.onclick = () => App.triggerFileByCurrentModule();
    document.body.appendChild(btn);
  },

  triggerFileByCurrentModule() {
    if (!App.state.module) return;
    App.triggerCamera(App.state.module);
  },

  parseRoute() {
    return App.state.module;
  },


  async searchWarehouse() {
    const query = (document.getElementById('warehouseSearch')?.value || '').trim();
    if (!query) {
      App.toast('請輸入關鍵字', '', 'warn');
      return;
    }
    try {
      const a = await App.fetchJSON('/api/warehouse?zone=A');
      const b = await App.fetchJSON('/api/warehouse?zone=B');
      const all = [...(a.bands || []), ...(b.bands || [])];
      let hit = null;
      for (const band of all) {
        for (const rowLabel of ['front','back']) {
          const arr = rowLabel === 'front' ? band.front : band.back;
          for (let i = 0; i < arr.length; i++) {
            const slot = arr[i];
            if (!slot) continue;
            const text = `${slot.customer_name || ''} ${slot.product || ''} ${slot.slot_key || ''}`;
            if (text.includes(query)) {
              hit = { zone: slot.zone, band: slot.band_no, row: slot.row_label, cell: slot.cell_no };
              break;
            }
          }
          if (hit) break;
        }
        if (hit) break;
      }
      if (hit) {
        App.showZone(hit.zone || 'A');
        App.toast('找到格位', `${hit.zone}-${hit.band}-${hit.row}-${hit.cell}`, 'good');
        App.openCellEditor(hit.zone, hit.band, hit.row, hit.cell);
      } else {
        App.toast('找不到', query, 'warn');
      }
    } catch (e) {
      App.toast('搜尋失敗', e.message, 'bad');
    }
  },

  init() {
    if (!window.APP_CONFIG || !window.APP_CONFIG.user) return;
    App.initModule();
    App.attachCameraButton();
    setInterval(() => App.poll(), 5000);
    setTimeout(() => App.poll(), 1200);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }
});
