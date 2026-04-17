(() => {
  const body = document.body;
  const page = body.dataset.page || '';
  const user = body.dataset.user || '';

  const qs = (s, root = document) => root.querySelector(s);
  const qsa = (s, root = document) => Array.from(root.querySelectorAll(s));

  function toast(msg) {
    const el = qs('#toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
  }

  async function apiJSON(url, options = {}) {
    const init = {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      credentials: 'same-origin',
      ...options,
    };
    const res = await fetch(url, init);
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (res.status === 401) {
      window.location.href = '/login';
      return null;
    }
    return data;
  }

  async function apiForm(url, formData) {
    const res = await fetch(url, { method: 'POST', body: formData, credentials: 'same-origin' });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (res.status === 401) {
      window.location.href = '/login';
      return null;
    }
    return data;
  }

  function escapeHTML(text) {
    return String(text ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function normalizeLine(line) {
    return String(line || '').trim();
  }

  function parseItemsFromText(text) {
    const lines = String(text || '')
      .split(/\n+/)
      .map(x => x.trim())
      .filter(Boolean);

    const items = [];
    for (const raw of lines) {
      const line = raw.replace(/[，,]/g, '').replace(/\s+/g, '');
      if (!line) continue;
      let m = line.match(/^(.+?)[=:x\*](\d+)$/i);
      if (!m) m = line.match(/^(.+?)\s+(\d+)$/);
      if (!m) m = line.match(/^(.+?)#(\d+)$/);
      if (!m) {
        items.push({ product: raw, quantity: 1 });
        continue;
      }
      let product = m[1].trim();
      let qty = parseInt(m[2], 10) || 1;
      if (!product) continue;
      items.push({ product, quantity: qty });
    }
    return items;
  }

  function groupCustomers(customers) {
    const groups = { '北區': [], '中區': [], '南區': [], '未分類': [] };
    for (const c of customers || []) {
      (groups[c.region || '未分類'] || groups['未分類']).push(c);
    }
    return groups;
  }

  function renderCustomerGroups(el, customers, opts = {}) {
    if (!el) return;
    const groups = groupCustomers(customers);
    const regionOrder = ['北區', '中區', '南區', '未分類'];
    el.innerHTML = regionOrder.map(region => {
      const items = (groups[region] || []).map(c => `
        <div class="customer-pill" draggable="true" data-name="${escapeHTML(c.name)}" data-region="${escapeHTML(c.region || region)}">
          ${escapeHTML(c.name)}
        </div>
      `).join('');
      return `
        <div class="customer-group" data-region="${region}">
          <div class="customer-group-head"><span>${region}</span><span>${(groups[region] || []).length}</span></div>
          <div class="customer-list">${items || '<span class="muted">尚無客戶</span>'}</div>
        </div>
      `;
    }).join('');

    const pills = qsa('.customer-pill', el);
    pills.forEach(pill => {
      pill.addEventListener('click', () => {
        const name = pill.dataset.name;
        const customer = (customers || []).find(c => c.name === name);
        if (customer) {
          selectCustomer(customer);
          if (opts.onSelect) opts.onSelect(customer);
        }
      });
      pill.addEventListener('dragstart', e => {
        e.dataTransfer.setData('text/plain', JSON.stringify({ name: pill.dataset.name, region: pill.dataset.region }));
        pill.classList.add('dragging');
      });
      pill.addEventListener('dragend', () => pill.classList.remove('dragging'));
    });

    qsa('.customer-list', el).forEach(list => {
      list.addEventListener('dragover', e => e.preventDefault());
      list.addEventListener('drop', async e => {
        e.preventDefault();
        const raw = e.dataTransfer.getData('text/plain');
        if (!raw) return;
        const payload = JSON.parse(raw);
        const dragged = qs(`.customer-pill[data-name="${CSS.escape(payload.name)}"]`, el);
        if (!dragged) return;
        list.appendChild(dragged);
        const region = list.closest('.customer-group').dataset.region;
        const orderedNames = qsa('.customer-pill', list).map(x => x.dataset.name);
        await apiJSON('/api/customers/reorder', {
          method: 'POST',
          body: JSON.stringify({ region, ordered_names: orderedNames })
        });
        const latest = await loadCustomers();
        renderCustomerGroups(el, latest, opts);
        toast('客戶排序已更新');
      });
    });
  }

  let currentCustomers = [];
  let currentCustomer = null;

  function setResult(html) {
    const box = qs('#result-box');
    if (box) box.innerHTML = html;
  }

  function selectCustomer(customer) {
    currentCustomer = customer;
    const input = qs('#customer-input');
    if (input) input.value = customer.name || '';
    const region = qs('#region-input');
    if (region && customer.region) region.value = customer.region;
    if (page === 'customers') {
      openCustomerDetail(customer);
    }
  }

  function openModal(title, bodyHTML, opts = {}) {
    const modal = qs('#modal');
    const modalTitle = qs('#modal-title');
    const modalBody = qs('#modal-body');
    if (!modal || !modalTitle || !modalBody) return;
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHTML;
    modal.classList.remove('hidden');
    modal.dataset.kind = opts.kind || '';
    if (opts.onOpen) opts.onOpen(modalBody);
  }

  function closeModal() {
    const modal = qs('#modal');
    if (modal) modal.classList.add('hidden');
  }

  function formatDateTime(value) {
    if (!value) return '';
    return String(value).replace('T', ' ').slice(0, 19);
  }

  async function loadCustomers() {
    const data = await apiJSON('/api/customers');
    currentCustomers = data?.customers || [];
    return currentCustomers;
  }

  async function loadInventory() {
    const data = await apiJSON('/api/inventory');
    return data?.items || [];
  }

  async function loadOrders() {
    const data = await apiJSON('/api/order');
    return data?.items || [];
  }

  async function loadMasterOrders() {
    const data = await apiJSON('/api/master_order');
    return data?.items || [];
  }

  function customerProductsSummary(customerName) {
    if (!customerName) return [];
    const agg = {};
    for (const o of window.__ordersCache || []) {
      if (o.customer === customerName) agg[o.product] = (agg[o.product] || 0) + Number(o.qty || 0);
    }
    for (const m of window.__masterOrdersCache || []) {
      if (m.customer === customerName) agg[m.product] = (agg[m.product] || 0) + Number(m.qty || 0);
    }
    return Object.entries(agg).map(([product, qty]) => ({ product, qty }));
  }

  function openCustomerDetail(customer) {
    const products = customerProductsSummary(customer.name);
    const html = `
      <div class="modal-body-grid single">
        <input class="text-input" id="m-name" value="${escapeHTML(customer.name || '')}" placeholder="客戶名稱" />
        <input class="text-input" id="m-phone" value="${escapeHTML(customer.phone || '')}" placeholder="電話" />
        <input class="text-input" id="m-address" value="${escapeHTML(customer.address || '')}" placeholder="地址" />
        <textarea class="ocr-box small" id="m-special" placeholder="特殊要求">${escapeHTML(customer.special_requirements || '')}</textarea>
        <select class="text-input select-input" id="m-region">
          ${['北區','中區','南區','未分類'].map(r => `<option value="${r}" ${String(customer.region || '未分類')===r ? 'selected' : ''}>${r}</option>`).join('')}
        </select>
      </div>
      <div class="button-row">
        <button class="primary-btn" id="modal-save-customer">儲存</button>
        <button class="secondary-btn" id="modal-delete-customer">刪除</button>
      </div>
      <div class="customer-products">
        <h4 style="margin:4px 0 8px;">所有商品</h4>
        ${products.length ? products.map(p => `<div class="product-row"><span>${escapeHTML(p.product)}</span><strong>${p.qty}</strong></div>`).join('') : '<div class="muted">目前沒有資料</div>'}
      </div>
    `;
    openModal('客戶明細', html, { kind: 'customer' });
    qs('#modal-save-customer').addEventListener('click', async () => {
      const payload = {
        name: qs('#m-name').value.trim(),
        phone: qs('#m-phone').value.trim(),
        address: qs('#m-address').value.trim(),
        special_requirements: qs('#m-special').value.trim(),
        region: qs('#m-region').value,
      };
      const res = await apiJSON('/api/customers', { method: 'POST', body: JSON.stringify(payload) });
      if (res?.success) {
        toast('客戶已更新');
        closeModal();
        await refreshCustomersUI();
      } else toast(res?.error || '儲存失敗');
    });
    qs('#modal-delete-customer').addEventListener('click', async () => {
      if (!confirm('確定刪除這個客戶嗎？')) return;
      const res = await apiJSON('/api/customers/delete', { method: 'POST', body: JSON.stringify({ name: customer.name }) });
      if (res?.success) {
        toast('客戶已刪除');
        closeModal();
        await refreshCustomersUI();
      } else toast(res?.error || '刪除失敗');
    });
  }

  async function refreshCustomersUI() {
    const customers = await loadCustomers();
    const groupEl = qs('#customer-groups');
    const adminEl = qs('#customer-admin-list');
    if (groupEl) renderCustomerGroups(groupEl, customers, { onSelect: () => {} });
    if (adminEl) renderCustomerAdmin(adminEl, customers);
    return customers;
  }

  function renderCustomerAdmin(el, customers) {
    if (!el) return;
    const groups = groupCustomers(customers);
    const html = ['北區', '中區', '南區', '未分類'].map(region => {
      const items = (groups[region] || []).map(c => `
        <div class="customer-pill" draggable="true" data-name="${escapeHTML(c.name)}" data-region="${escapeHTML(region)}">${escapeHTML(c.name)}</div>
      `).join('');
      return `
        <div class="customer-group" data-region="${region}">
          <div class="customer-group-head"><span>${region}</span><span>${(groups[region] || []).length}</span></div>
          <div class="customer-list">${items || '<span class="muted">尚無客戶</span>'}</div>
        </div>
      `;
    }).join('');
    el.innerHTML = html;

    qsa('.customer-pill', el).forEach(pill => {
      pill.addEventListener('click', () => {
        const c = (customers || []).find(x => x.name === pill.dataset.name);
        if (c) openCustomerDetail(c);
      });
      pill.addEventListener('dragstart', e => {
        e.dataTransfer.setData('text/plain', JSON.stringify({ name: pill.dataset.name, region: pill.dataset.region }));
      });
    });
    qsa('.customer-list', el).forEach(list => {
      list.addEventListener('dragover', e => e.preventDefault());
      list.addEventListener('drop', async e => {
        e.preventDefault();
        const payload = JSON.parse(e.dataTransfer.getData('text/plain'));
        const dragged = qs(`.customer-pill[data-name="${CSS.escape(payload.name)}"]`, el);
        if (!dragged) return;
        list.appendChild(dragged);
        const region = list.closest('.customer-group').dataset.region;
        const orderedNames = qsa('.customer-pill', list).map(x => x.dataset.name);
        await apiJSON('/api/customers/reorder', { method: 'POST', body: JSON.stringify({ region, ordered_names: orderedNames }) });
        await refreshCustomersUI();
        toast('已更新排序');
      });
    });
  }

  async function initAuthPage() {
    const usernameEl = qs('#login-username');
    const passwordEl = qs('#login-password');
    const rememberEl = qs('#remember-me');
    const msg = qs('#login-msg');
    const btn = qs('#login-btn');
    const savedUser = localStorage.getItem('username') || '';
    const savedPass = localStorage.getItem('password') || '';
    if (usernameEl && savedUser) usernameEl.value = savedUser;
    if (passwordEl && savedPass) passwordEl.value = savedPass;

    async function submitLogin() {
      const username = usernameEl.value.trim();
      const password = passwordEl.value.trim();
      msg.textContent = '';
      if (!username || !password) {
        msg.textContent = '請輸入帳號與密碼';
        return;
      }
      btn.disabled = true;
      btn.textContent = '登入中...';
      const res = await apiJSON('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      btn.disabled = false;
      btn.textContent = '登入系統';
      if (res?.success) {
        localStorage.setItem('username', username);
        if (rememberEl.checked) localStorage.setItem('password', password);
        else localStorage.removeItem('password');
        window.location.href = '/';
      } else {
        msg.textContent = res?.error || '登入失敗';
      }
    }

    btn?.addEventListener('click', submitLogin);
    [usernameEl, passwordEl].forEach(el => el?.addEventListener('keydown', e => {
      if (e.key === 'Enter') submitLogin();
    }));

    if (savedUser && savedPass) {
      // try auto-login to keep session persistent
      const res = await apiJSON('/api/login', { method: 'POST', body: JSON.stringify({ username: savedUser, password: savedPass }) });
      if (res?.success) window.location.href = '/';
    }
  }

  async function initHome() {
    qs('#logout-btn')?.addEventListener('click', async () => {
      await apiJSON('/api/logout', { method: 'POST', body: '{}' });
      localStorage.removeItem('password');
      window.location.href = '/login';
    });
  }

  function renderInventoryList(items) {
    setResult(`
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>商品</th><th>數量</th><th>格位</th><th>操作人員</th><th>時間</th></tr></thead>
          <tbody>
            ${items.map(i => `<tr><td>${escapeHTML(i.product)}</td><td>${escapeHTML(i.quantity)}</td><td>${escapeHTML(i.location || '')}</td><td>${escapeHTML(i.operator || '')}</td><td>${escapeHTML(i.updated_at || '')}</td></tr>`).join('') || '<tr><td colspan="5">尚無資料</td></tr>'}
          </tbody>
        </table>
      </div>
    `);
  }

  function renderOrdersList(items) {
    setResult(`
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>客戶</th><th>商品</th><th>數量</th><th>狀態</th><th>操作人員</th><th>時間</th></tr></thead>
          <tbody>
            ${items.map(i => `<tr><td>${escapeHTML(i.customer)}</td><td>${escapeHTML(i.product)}</td><td>${escapeHTML(i.qty)}</td><td>${escapeHTML(i.status)}</td><td>${escapeHTML(i.operator || '')}</td><td>${escapeHTML(i.created_at || '')}</td></tr>`).join('') || '<tr><td colspan="6">尚無資料</td></tr>'}
          </tbody>
        </table>
      </div>
    `);
  }

  function renderMasterOrdersList(items) {
    setResult(`
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>客戶</th><th>商品</th><th>數量</th><th>操作人員</th><th>時間</th></tr></thead>
          <tbody>
            ${items.map(i => `<tr><td>${escapeHTML(i.customer)}</td><td>${escapeHTML(i.product)}</td><td>${escapeHTML(i.qty)}</td><td>${escapeHTML(i.operator || '')}</td><td>${escapeHTML(i.updated_at || '')}</td></tr>`).join('') || '<tr><td colspan="5">尚無資料</td></tr>'}
          </tbody>
        </table>
      </div>
    `);
  }

  async function uploadOCR(fileInput, statusEl, confEl) {
    const file = fileInput.files?.[0];
    if (!file) return null;
    statusEl.textContent = '辨識中...';
    confEl.textContent = '信心值：...';
    const fd = new FormData();
    fd.append('file', file);
    const data = await apiForm('/api/upload_ocr', fd);
    if (!data) return null;
    if (data.success) {
      qs('#ocr-text').value = data.text || '';
      statusEl.textContent = '辨識完成';
      confEl.textContent = `信心值：${data.confidence ?? 0}`;
      if (data.warning) toast(data.warning);
      return data;
    }
    statusEl.textContent = data.error || 'OCR失敗';
    toast(data.error || 'OCR失敗');
    return null;
  }

  function getModulePayload() {
    const text = qs('#ocr-text')?.value || '';
    const items = parseItemsFromText(text);
    return {
      customer: qs('#customer-input')?.value.trim() || '',
      region: qs('#region-input')?.value || '未分類',
      location: qs('#location-input')?.value.trim() || '',
      items,
    };
  }

  function renderOperationResult(pageKey, res) {
    if (!res) return;
    if (!res.success) {
      setResult(`<div class="result-box">${escapeHTML(res.error || '操作失敗')}</div>`);
      toast(res.error || '操作失敗');
      return;
    }
    if (pageKey === 'inventory') {
      renderInventoryList(res.inventory || []);
      toast(res.message || '庫存已更新');
      return;
    }
    if (pageKey === 'order') {
      renderOrdersList(res.orders || []);
      setResult(`<div class="result-box">客戶：${escapeHTML(qs('#customer-input')?.value || '')}<br>狀態：pending<br>已建立訂單</div>`);
      toast(res.message || '訂單已建立');
      return;
    }
    if (pageKey === 'master_order') {
      renderMasterOrdersList(res.master_orders || []);
      setResult(`<div class="result-box">客戶：${escapeHTML(qs('#customer-input')?.value || '')}<br>已更新總單</div>`);
      toast(res.message || '總單已更新');
      return;
    }
    if (pageKey === 'ship') {
      const details = (res.details || []).map(d => `<div class="product-row"><span>${escapeHTML(d.customer)}｜${escapeHTML(d.product)}</span><strong>${escapeHTML(d.detail)}</strong></div>`).join('');
      setResult(`<div class="result-box"><strong>出貨完成</strong><div style="margin-top:10px;display:flex;flex-direction:column;gap:8px;">${details || '<div class="muted">無資料</div>'}</div></div>`);
      toast(res.message || '出貨成功');
    }
  }

  async function initModulePage() {
    qs('#logout-btn')?.addEventListener('click', async () => {
      await apiJSON('/api/logout', { method: 'POST', body: '{}' });
      localStorage.removeItem('password');
      window.location.href = '/login';
    });
    qs('#modal-close')?.addEventListener('click', closeModal);
    window.__ordersCache = await loadOrders();
    window.__masterOrdersCache = await loadMasterOrders();
    qs('#modal')?.addEventListener('click', e => {
      if (e.target.id === 'modal') closeModal();
    });

    if (['inventory','order','master_order','ship'].includes(page)) {
      const fileInput = qs('#file-input');
      const statusEl = qs('#upload-status');
      const confEl = qs('#confidence-pill');
      const confirmBtn = qs('#confirm-btn');
      const clearBtn = qs('#clear-btn');
      const customerGroups = qs('#customer-groups');
      qs('#operator-input').value = user || localStorage.getItem('username') || '';
      fileInput?.addEventListener('change', async () => {
        await uploadOCR(fileInput, statusEl, confEl);
      });
      confirmBtn?.addEventListener('click', async () => {
        const payload = getModulePayload();
        if (!payload.items.length) {
          toast('沒有可送出的商品');
          return;
        }
        if (page === 'inventory') {
          const res = await apiJSON('/api/inventory', { method: 'POST', body: JSON.stringify({ items: payload.items }) });
          renderOperationResult(page, res);
        } else if (page === 'order') {
          const res = await apiJSON('/api/order', { method: 'POST', body: JSON.stringify({ customer: payload.customer, items: payload.items }) });
          renderOperationResult(page, res);
        } else if (page === 'master_order') {
          const res = await apiJSON('/api/master_order', { method: 'POST', body: JSON.stringify({ customer: payload.customer, items: payload.items }) });
          renderOperationResult(page, res);
        } else if (page === 'ship') {
          if (!confirm(`確認要為「${payload.customer}」出貨嗎？`)) return;
          const res = await apiJSON('/api/ship', { method: 'POST', body: JSON.stringify({ customer: payload.customer, items: payload.items, confirm: true }) });
          renderOperationResult(page, res);
        }
        await refreshCustomersUI();
      });
      clearBtn?.addEventListener('click', () => {
        qs('#ocr-text').value = '';
        qs('#customer-input').value = '';
        qs('#location-input').value = '';
        qs('#file-input').value = '';
        setResult('');
        statusEl.textContent = '尚未上傳';
        confEl.textContent = '信心值：—';
      });
      const customers = await refreshCustomersUI();
      if (customerGroups && customers.length) renderCustomerGroups(customerGroups, customers, { onSelect: selectCustomer });
      if (customerGroups) {
        const selected = qs('#customer-input');
        selected?.addEventListener('input', () => {
          const c = customers.find(x => x.name === selected.value.trim());
          if (c) selectCustomer(c);
        });
      }
      // caches for customer product summaries
      window.__ordersCache = await loadOrders();
      window.__masterOrdersCache = await loadMasterOrders();
    }

    if (page === 'shipping_records') {
      const tbody = qs('#shipping-tbody');
      const filter = qs('#days-filter');
      const button = qs('#query-shipping-btn');
      async function loadRecords() {
        const days = filter.value;
        const data = await apiJSON(`/api/shipping_records?days=${encodeURIComponent(days)}`);
        const rows = data?.records || [];
        tbody.innerHTML = rows.map(r => `
          <tr>
            <td>${escapeHTML(r.shipped_at || '')}</td>
            <td>${escapeHTML(r.customer || '')}</td>
            <td>${escapeHTML(r.product || '')}</td>
            <td>${escapeHTML(r.qty || '')}</td>
            <td>${escapeHTML(r.operator || '')}</td>
            <td>${escapeHTML(r.deduction_detail || '')}</td>
          </tr>
        `).join('') || '<tr><td colspan="6">尚無資料</td></tr>';
      }
      button?.addEventListener('click', loadRecords);
      filter?.addEventListener('change', loadRecords);
      await loadRecords();
    }

    if (page === 'customers') {
      const list = qs('#customer-admin-list');
      const saveBtn = qs('#save-customer-btn');
      const deleteBtn = qs('#delete-customer-btn');
      const detailEmpty = qs('#customer-detail-empty');
      const detailForm = qs('#customer-detail-form');
      let selected = null;

      function updateDetailVisibility(show) {
        detailEmpty.classList.toggle('hidden', show);
        detailForm.classList.toggle('hidden', !show);
      }

      window.__customerProducts = [];
      const renderList = async () => {
        const customers = await refreshCustomersUI();
        list.innerHTML = '';
        renderCustomerAdmin(list, customers);
        qsa('.customer-pill', list).forEach(pill => {
          pill.addEventListener('click', () => {
            selected = customers.find(c => c.name === pill.dataset.name);
            if (!selected) return;
            updateDetailVisibility(true);
            qs('#detail-name').value = selected.name || '';
            qs('#detail-phone').value = selected.phone || '';
            qs('#detail-address').value = selected.address || '';
            qs('#detail-special').value = selected.special_requirements || '';
            qs('#detail-region').value = selected.region || '未分類';
            const products = customerProductsSummary(selected.name);
            const box = qs('#customer-products');
            box.innerHTML = products.map(p => `<div class="product-row"><span>${escapeHTML(p.product)}</span><strong>${p.qty}</strong></div>`).join('') || '<div class="muted">目前沒有商品</div>';
          });
        });
      };

      saveBtn?.addEventListener('click', async () => {
        const payload = {
          name: qs('#detail-name').value.trim(),
          phone: qs('#detail-phone').value.trim(),
          address: qs('#detail-address').value.trim(),
          special_requirements: qs('#detail-special').value.trim(),
          region: qs('#detail-region').value,
        };
        const res = await apiJSON('/api/customers', { method: 'POST', body: JSON.stringify(payload) });
        if (res?.success) {
          toast('客戶已儲存');
          selected = payload;
          await renderList();
        } else toast(res?.error || '儲存失敗');
      });
      deleteBtn?.addEventListener('click', async () => {
        if (!selected) return;
        if (!confirm(`確定刪除 ${selected.name}？`)) return;
        const res = await apiJSON('/api/customers/delete', { method: 'POST', body: JSON.stringify({ name: selected.name }) });
        if (res?.success) {
          toast('客戶已刪除');
          selected = null;
          updateDetailVisibility(false);
          await renderList();
        } else toast(res?.error || '刪除失敗');
      });
      updateDetailVisibility(false);
      await renderList();
    }

    if (page === 'warehouse') {
      const grid = qs('#warehouse-grid');
      const addBtn = qs('#add-warehouse-cell-btn');
      const refreshBtn = qs('#refresh-warehouse-btn');

      async function loadAndRender() {
        const data = await apiJSON('/api/warehouse');
        const cells = data?.cells || [];
        const byArea = { A: [], B: [] };
        for (const c of cells) (byArea[c.area] || byArea['A']).push(c);

        function cellOf(area, col, pos) {
          return cells.find(x => x.area === area && Number(x.col_no) === col && x.position === pos) || { area, col_no: col, position: pos, label: `${area}${col}-${pos}`, customer_name: '', product: '', quantity: 0, note: '' };
        }

        grid.innerHTML = ['A', 'B'].map(area => `
          <section class="warehouse-area">
            <div class="warehouse-area-head">
              <span>${area} 區</span>
              <div class="warehouse-actions-inline">
                <button class="secondary-btn add-area-cell" data-area="${area}">新增格位</button>
              </div>
            </div>
            <table class="warehouse-table">
              <thead>
                <tr>
                  ${[1,2,3,4,5,6].map(n => `<th>${n} 欄</th>`).join('')}
                </tr>
              </thead>
              <tbody>
                <tr>
                  ${[1,2,3,4,5,6].map(col => {
                    const front = cellOf(area, col, 'front');
                    return `<td>
                      <div class="warehouse-cell ${front.product ? '' : 'empty'}" data-area="${area}" data-col="${col}" data-position="front">
                        <div><small>前</small><br><strong>${escapeHTML(front.label || `${area}${col} 前`)}</strong></div>
                        <div class="qty">${escapeHTML(front.customer_name || '尚未設定')}</div>
                        <div class="qty">${escapeHTML(front.product || '')}</div>
                        <div class="qty">庫存：${escapeHTML(front.quantity || 0)}</div>
                      </div>
                    </td>`;
                  }).join('')}
                </tr>
                <tr>
                  ${[1,2,3,4,5,6].map(col => {
                    const back = cellOf(area, col, 'back');
                    return `<td>
                      <div class="warehouse-cell ${back.product ? '' : 'empty'}" data-area="${area}" data-col="${col}" data-position="back">
                        <div><small>後</small><br><strong>${escapeHTML(back.label || `${area}${col} 後`)}</strong></div>
                        <div class="qty">${escapeHTML(back.customer_name || '尚未設定')}</div>
                        <div class="qty">${escapeHTML(back.product || '')}</div>
                        <div class="qty">庫存：${escapeHTML(back.quantity || 0)}</div>
                      </div>
                    </td>`;
                  }).join('')}
                </tr>
              </tbody>
            </table>
          </section>
        `).join('');

        qsa('.warehouse-cell', grid).forEach(cell => {
          cell.addEventListener('click', () => openWarehouseCellModal(cells, cell.dataset.area, Number(cell.dataset.col), cell.dataset.position));
        });
        qsa('.add-area-cell', grid).forEach(btn => {
          btn.addEventListener('click', () => openWarehouseCellModal(cells, btn.dataset.area, 1, 'front', true));
        });
      }

      function openWarehouseCellModal(cells, area, col, position, createNew = false) {
        const existing = cells.find(x => x.area === area && Number(x.col_no) === Number(col) && x.position === position) || { area, col_no: col, position, label: `${area}${col}-${position}`, customer_name: '', product: '', quantity: 0, note: '' };
        const html = `
          <div class="modal-body-grid single">
            <div class="form-row">
              <input id="w-area" class="text-input" value="${escapeHTML(existing.area)}" placeholder="A/B" />
              <input id="w-col" class="text-input" type="number" value="${escapeHTML(existing.col_no)}" min="1" max="6" />
            </div>
            <div class="form-row">
              <select id="w-pos" class="text-input select-input">
                <option value="front" ${existing.position === 'front' ? 'selected' : ''}>前</option>
                <option value="back" ${existing.position === 'back' ? 'selected' : ''}>後</option>
              </select>
              <input id="w-label" class="text-input" value="${escapeHTML(existing.label || '')}" placeholder="格位名稱" />
            </div>
            <input id="w-customer" class="text-input" value="${escapeHTML(existing.customer_name || '')}" placeholder="客戶名稱" />
            <input id="w-product" class="text-input" value="${escapeHTML(existing.product || '')}" placeholder="商品" />
            <input id="w-qty" class="text-input" type="number" value="${escapeHTML(existing.quantity || 0)}" min="0" placeholder="庫存數量" />
            <textarea id="w-note" class="ocr-box small" placeholder="備註">${escapeHTML(existing.note || '')}</textarea>
          </div>
          <div class="button-row">
            <button class="primary-btn" id="save-warehouse-cell">儲存</button>
            <button class="secondary-btn" id="delete-warehouse-cell">刪除</button>
          </div>
        `;
        openModal(createNew ? '新增格位' : '編輯格位', html, { kind: 'warehouse' });
        qs('#save-warehouse-cell').addEventListener('click', async () => {
          const payload = {
            area: qs('#w-area').value.trim().toUpperCase() || 'A',
            col_no: Number(qs('#w-col').value || 1),
            position: qs('#w-pos').value,
            label: qs('#w-label').value.trim(),
            customer_name: qs('#w-customer').value.trim(),
            product: qs('#w-product').value.trim(),
            quantity: Number(qs('#w-qty').value || 0),
            note: qs('#w-note').value.trim(),
          };
          const res = await apiJSON('/api/warehouse', { method: 'POST', body: JSON.stringify(payload) });
          if (res?.success) {
            toast('倉庫格位已更新');
            closeModal();
            await loadAndRender();
          } else toast(res?.error || '儲存失敗');
        });
        qs('#delete-warehouse-cell').addEventListener('click', async () => {
          if (!confirm('確定刪除這個格位嗎？')) return;
          const res = await apiJSON('/api/warehouse/delete', { method: 'POST', body: JSON.stringify({ area, col_no: col, position }) });
          if (res?.success) {
            toast('格位已刪除');
            closeModal();
            await loadAndRender();
          } else toast(res?.error || '刪除失敗');
        });
      }

      addBtn?.addEventListener('click', () => openWarehouseCellModal([], 'A', 1, 'front', true));
      refreshBtn?.addEventListener('click', loadAndRender);
      await loadAndRender();
    }

    if (page === 'settings') {
      const oldP = qs('#old-password');
      const newP = qs('#new-password');
      const confirmP = qs('#confirm-password');
      const changeBtn = qs('#change-password-btn');
      const backupBtn = qs('#backup-btn');
      const reloadBackupsBtn = qs('#reload-backups-btn');
      const backupList = qs('#backup-list');

      async function loadBackups() {
        const data = await apiJSON('/api/backups');
        const files = data?.files || [];
        backupList.innerHTML = files.map(f => `
          <div class="backup-item">
            <h4>${escapeHTML(f.filename)}</h4>
            <p>時間：${escapeHTML(f.created_at)}｜大小：${Math.round((f.size || 0) / 1024)} KB</p>
          </div>
        `).join('') || '<div class="muted">尚無備份</div>';
      }

      changeBtn?.addEventListener('click', async () => {
        const res = await apiJSON('/api/change_password', {
          method: 'POST',
          body: JSON.stringify({
            old_password: oldP.value.trim(),
            new_password: newP.value.trim(),
            confirm_password: confirmP.value.trim(),
          }),
        });
        if (res?.success) {
          toast('密碼已更新');
          oldP.value = newP.value = confirmP.value = '';
        } else toast(res?.error || '修改失敗');
      });
      backupBtn?.addEventListener('click', async () => {
        const res = await apiJSON('/api/backup', { method: 'POST', body: '{}' });
        if (res?.success) {
          toast('備份完成');
          await loadBackups();
        } else toast(res?.error || '備份失敗');
      });
      reloadBackupsBtn?.addEventListener('click', loadBackups);
      await loadBackups();
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    if (qs('#login-btn')) {
      await initAuthPage();
      return;
    }
    if (qs('#logout-btn') && qs('.home-menu')) {
      await initHome();
      return;
    }
    await initModulePage();
  });
})();
