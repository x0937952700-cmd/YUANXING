(function(){
  const state = {
    currentPage: window.APP_BOOT?.page || "home",
    module: window.APP_BOOT?.module || "",
    user: window.APP_BOOT?.user || "",
    badge: Number(window.APP_BOOT?.badge || 0),
    zone: "A",
    warehouseSearch: "",
    warehouseData: [],
    notifications: [],
    latestNotificationId: 0,
    customers: [],
    inventory: [],
    ocrItems: [],
    currentOcrText: "",
    currentConfidence: 0,
    lastTodayHash: ""
  };

  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  function escapeHtml(s){
    return String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function toast(msg){
    const stack = $("#toastStack");
    if(!stack) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    stack.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateY(-10px)"; }, 2200);
    setTimeout(() => el.remove(), 2800);
  }

  function openModal(sel){
    const m = $(sel);
    if(m) m.hidden = false;
  }
  function closeModal(sel){
    const m = $(sel);
    if(m) m.hidden = true;
  }

  async function api(url, options={}){
    const res = await fetch(url, {
      headers: {"X-Requested-With":"fetch"},
      ...options
    });
    if (res.headers.get("content-type")?.includes("application/json")) {
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data.error || "請求失敗");
      return data;
    }
    if (!res.ok) throw new Error("請求失敗");
    return res.text();
  }

  async function postJson(url, payload){
    return api(url, {
      method:"POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload || {})
    });
  }

  function wireCommon(){
    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-close]");
      if(btn){
        closeModal(btn.getAttribute("data-close"));
      }
      const modal = e.target.classList.contains("modal") ? e.target : null;
      if(modal) modal.hidden = true;
    });

    const settingsBtn = $("#settingsBtn");
    if(settingsBtn){
      settingsBtn.addEventListener("click", () => openModal("#settingsModal"));
    }
    const logoutBtn = $("#logoutBtn");
    if(logoutBtn){
      logoutBtn.addEventListener("click", async () => {
        await postJson("/api/logout", {});
        window.location.href = "/login";
      });
    }
    const todayBtn = $("#todayChangesBtn");
    if(todayBtn){
      todayBtn.addEventListener("click", async () => {
        openModal("#todayModal");
        await loadTodayModal();
      });
    }
    const savePasswordBtn = $("#savePasswordBtn");
    if(savePasswordBtn){
      savePasswordBtn.addEventListener("click", async () => {
        const old_password = $("#oldPassword").value.trim();
        const new_password = $("#newPassword").value.trim();
        const confirm = $("#confirmPassword").value.trim();
        const box = $("#passwordMsg");
        box.textContent = "";
        if(new_password !== confirm){
          box.textContent = "新密碼與確認密碼不一致";
          return;
        }
        try{
          await postJson("/api/change_password", {old_password, new_password});
          box.textContent = "密碼已更新";
          toast("密碼已更新");
          setTimeout(() => closeModal("#settingsModal"), 600);
        }catch(err){
          box.textContent = err.message;
        }
      });
    }
  }

  async function loadTodayModal(){
    const root = $("#todayModalContent");
    if(!root) return;
    const data = await api("/api/today_changes");
    const s = data.summary || {};
    const logs = data.logs || [];
    const notifications = data.notifications || [];
    refreshBadge(s.unread_notifications || 0);
    root.innerHTML = `
      <section class="summary-grid" style="margin-top:0">
        <div class="summary-card"><span>今日新增</span><strong>${s.new_count || 0}</strong></div>
        <div class="summary-card"><span>今日出貨量</span><strong>${s.ship_count || 0}</strong></div>
        <div class="summary-card"><span>未上架商品</span><strong>${s.unplaced_count || 0}</strong></div>
        <div class="summary-card"><span>異常紀錄</span><strong>${s.anomaly_count || 0}</strong></div>
      </section>
      <div class="hr"></div>
      <h4>通知列表</h4>
      <div class="detail-list">
        ${(notifications.length ? notifications : []).map(n => `
          <div class="detail-item">
            <div><strong>${escapeHtml(n.username || "系統")}</strong>｜${escapeHtml(n.message || "")}</div>
            <div class="meta">${escapeHtml(n.created_at || "")}｜${escapeHtml(n.kind || "")}</div>
          </div>
        `).join("") || '<div class="muted">今日沒有通知</div>'}
      </div>
      <div class="hr"></div>
      <h4>操作歷史</h4>
      <div class="detail-list">
        ${(logs.length ? logs : []).map(log => `
          <div class="detail-item">
            <div><strong>${escapeHtml(log.username || "")}</strong>｜${escapeHtml(log.action || "")}</div>
            <div class="meta">${escapeHtml(log.created_at || "")}｜${escapeHtml(log.target_type || "")} ${escapeHtml(log.target_name || "")}</div>
          </div>
        `).join("") || '<div class="muted">今日沒有操作紀錄</div>'}
      </div>
    `;
  }

  async function pollNotifications(){
    try{
      const data = await api("/api/notifications?limit=50");
      const items = data.items || [];
      if(!items.length) return;
      const latest = items[0].id;
      if(state.latestNotificationId && latest > state.latestNotificationId){
        const newItems = items.filter(i => i.id > state.latestNotificationId).reverse();
        newItems.forEach(i => toast(i.message || "有新通知"));
        state.latestNotificationId = latest;
        refreshBadge(items.filter(i => i.read_flag == 0).length);
      }else if(!state.latestNotificationId){
        state.latestNotificationId = latest;
        refreshBadge(items.filter(i => i.read_flag == 0).length);
      }
    }catch(e){}
  }

  function refreshBadge(count){
    const btn = $("#todayChangesBtn");
    if(btn) btn.setAttribute("data-badge", String(count || 0));
  }

  async function renderHomeExtras(){
    await pollNotifications();
    setInterval(pollNotifications, 6000);
  }

  // ===== modules =====
  async function initModule(){
    const module = state.module;
    const root = $("#moduleRoot");
    const title = $("#moduleTitle");
    if(!root || !title) return;

    const titles = {
      inventory: "庫存",
      orders: "訂單",
      master_orders: "總單",
      shipping: "出貨",
      shipping_records: "出貨查詢",
      warehouse: "倉庫圖",
      customers: "客戶資料",
      today_changes: "今日異動"
    };
    title.textContent = titles[module] || "模組";

    if(module === "inventory") return renderInventory();
    if(module === "orders") return renderOrder("orders");
    if(module === "master_orders") return renderOrder("master_orders");
    if(module === "shipping") return renderShipping();
    if(module === "shipping_records") return renderShippingRecords();
    if(module === "warehouse") return renderWarehouse();
    if(module === "customers") return renderCustomers();
    if(module === "today_changes") return renderTodayChanges();
  }

  function fileUploaderHtml(mode){
    return `
      <div class="upload-area">
        <div class="upload-actions">
          <button class="btn primary" data-album-btn="${mode}">上傳檔案（相簿 / 拍照）</button>
          <button class="btn secondary" data-camera-btn="${mode}">拍照上傳</button>
          <span class="confidence-chip" id="${mode}ConfidenceChip">信心值：0%</span>
          <button class="btn ghost small" data-reset-ocr="${mode}">重新整理</button>
        </div>
        <input class="file-input" type="file" accept="image/*" id="${mode}AlbumInput">
        <input class="file-input" type="file" accept="image/*" capture="environment" id="${mode}CameraInput">
      </div>
    `;
  }

  async function handleOCRUpload(mode, file){
    const form = new FormData();
    form.append("file", file);
    // Optional: if you later add crop selection, these can be sent too.
    const customer = $(`#${mode}Customer`);
    if(customer) form.append("customer_keyword", customer.value.trim());

    const res = await fetch("/api/upload_ocr", {method:"POST", body:form});
    const data = await res.json();
    if(!res.ok || data.success === false) throw new Error(data.error || "OCR失敗");
    state.currentOcrText = data.text || "";
    state.currentConfidence = Number(data.confidence || 0);
    state.ocrItems = data.items || [];
    const chip = $(`#${mode}ConfidenceChip`);
    if(chip) chip.textContent = `信心值：${state.currentConfidence}%`;
    const box = $(`#${mode}OcrText`);
    if(box) box.value = state.currentOcrText;
    const warn = $(`#${mode}Warning`);
    if(warn) warn.textContent = data.warning || "";
    const cust = $(`#${mode}Customer`);
    if(cust && data.customer_name) cust.value = data.customer_name;
    if(data.warning) toast(data.warning);
  }

  function bindUploadButtons(mode){
    const albumBtn = $(`[data-album-btn="${mode}"]`);
    const cameraBtn = $(`[data-camera-btn="${mode}"]`);
    const albumInput = $(`#${mode}AlbumInput`);
    const cameraInput = $(`#${mode}CameraInput`);
    albumBtn?.addEventListener("click", () => albumInput?.click());
    cameraBtn?.addEventListener("click", () => cameraInput?.click());
    albumInput?.addEventListener("change", async () => {
      const file = albumInput.files?.[0];
      if(file) await handleOCRUpload(mode, file).catch(err => toast(err.message));
      albumInput.value = "";
    });
    cameraInput?.addEventListener("change", async () => {
      const file = cameraInput.files?.[0];
      if(file) await handleOCRUpload(mode, file).catch(err => toast(err.message));
      cameraInput.value = "";
    });
    $(`[data-reset-ocr="${mode}"]`)?.addEventListener("click", () => {
      const box = $(`#${mode}OcrText`);
      if(box) box.value = "";
      const warn = $(`#${mode}Warning`);
      if(warn) warn.textContent = "";
    });
  }

  async function renderInventory(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>庫存</h3>
            <div class="muted">直接顯示商品，不顯示客戶分類。</div>
          </div>
          <div class="search-row">
            <input id="invSearch" placeholder="搜尋商品 / 格位">
            <button class="btn secondary" id="invRefresh">重新整理</button>
          </div>
        </div>
        <div id="inventoryPanel" class="list"></div>
      </section>
    `;
    const load = async () => {
      const data = await api("/api/inventory");
      state.inventory = data.items || [];
      const q = ($("#invSearch").value || "").trim().toLowerCase();
      const filtered = state.inventory.filter(i =>
        !q || [i.product, i.location, i.customer_name].join(" ").toLowerCase().includes(q)
      );
      $("#inventoryPanel").innerHTML = filtered.map(item => `
        <div class="card ${item.unplaced_qty > 0 ? 'red' : ''}">
          <div class="top-bar">
            <div>
              <div><strong>${escapeHtml(item.product || "")}</strong> ${item.unplaced_qty > 0 ? '<span class="badge red">未上架</span>' : '<span class="badge green">已上架</span>'}</div>
              <div class="meta">數量：${item.quantity || 0}｜格位：${escapeHtml(item.location || "-")}${item.customer_name ? `｜客戶：${escapeHtml(item.customer_name)}` : ""}</div>
            </div>
            <div class="badge ${item.unplaced_qty > 0 ? 'red' : 'gray'}">未上架 ${item.unplaced_qty || 0}</div>
          </div>
          <div class="meta">操作人員：${escapeHtml(item.operator || "-")}｜更新：${escapeHtml(item.updated_at || "-")}</div>
        </div>
      `).join("") || '<div class="muted">沒有庫存資料</div>';
    };
    $("#invSearch").addEventListener("input", load);
    $("#invRefresh").addEventListener("click", load);
    await load();
    setInterval(load, 8000);
  }

  function orderEditorHtml(mode){
    const title = mode === "orders" ? "訂單" : "總單";
    return `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>${title}</h3>
            <div class="muted">${mode === "orders" ? "建立後預設為 pending；出貨時會依序扣總單、訂單、庫存。" : "總單頁不要顯示客戶名稱。"} </div>
          </div>
        </div>

        <div class="upload-row">
          ${fileUploaderHtml(mode)}
        </div>

        <div class="grid cols-2">
          <div>
            <label>客戶名稱 ${mode === "master_orders" ? '(可隱藏顯示)' : ''}</label>
            <input id="${mode}Customer" placeholder="輸入客戶名稱，會自動比對最像的客戶">
            <div class="muted small">輸入關鍵字會跳出完整客戶名。</div>
            <div id="${mode}CustomerSuggest" class="chips" style="margin-top:10px"></div>
          </div>
          <div>
            <label>格位 / 備註（可選）</label>
            <input id="${mode}Location" placeholder="例如：A區1欄前6">
          </div>
        </div>

        <label>OCR 文字框（可人工修改）</label>
        <textarea id="${mode}OcrText" placeholder="辨識後內容會直接進來，你可自行編輯"></textarea>
        <div class="upload-meta">
          <span id="${mode}Warning" class="confidence-chip" style="display:inline-flex">尚未辨識</span>
        </div>

        <div class="grid cols-2" style="margin-top:14px">
          <button class="btn primary" id="${mode}ConfirmBtn">確認送出</button>
          <button class="btn secondary" id="${mode}SaveCorrectionBtn">記錄 AI 修正</button>
        </div>

        <div class="hr"></div>
        <div id="${mode}Result"></div>
      </section>
    `;
  }

  async function renderOrder(mode){
    const root = $("#moduleRoot");
    root.innerHTML = orderEditorHtml(mode);
    bindUploadButtons(mode);
    const suggestEl = $(`#${mode}CustomerSuggest`);
    const customerEl = $(`#${mode}Customer`);
    const textEl = $(`#${mode}OcrText`);
    const warnEl = $(`#${mode}Warning`);
    const resultEl = $(`#${mode}Result`);

    customerEl.addEventListener("input", async () => {
      const q = customerEl.value.trim();
      if(!q) { suggestEl.innerHTML = ""; return; }
      try{
        const data = await api(`/api/customers/suggest?q=${encodeURIComponent(q)}`);
        suggestEl.innerHTML = (data.customers || []).map(c => `<button class="chip" data-pick-customer="${mode}" data-name="${escapeHtml(c.name)}">${escapeHtml(c.name)}</button>`).join("");
      }catch(e){}
    });
    suggestEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-pick-customer]");
      if(!btn) return;
      customerEl.value = btn.dataset.name;
      suggestEl.innerHTML = "";
    });

    $(`#${mode}ConfirmBtn`).addEventListener("click", async () => {
      try{
        const items = parseTextToItems(textEl.value);
        const customer_name = customerEl.value.trim();
        if(!items.length) throw new Error("請先 OCR 或輸入內容");
        const payload = {customer_name, items};
        const endpoint = mode === "orders" ? "/api/orders/save" : "/api/master_orders/save";
        const data = await postJson(endpoint, payload);
        resultEl.innerHTML = `
          <div class="card">
            <strong>已送出</strong>
            <div class="meta">${mode === "orders" ? "訂單建立完成" : "總單已更新"}</div>
            <div class="detail-list" style="margin-top:10px">
              ${items.map(i => `<div class="detail-item">${escapeHtml(i.product)} × ${i.quantity}</div>`).join("")}
            </div>
          </div>
        `;
        toast("已送出");
        await pollNotifications();
      }catch(err){ toast(err.message); }
    });

    $(`#${mode}SaveCorrectionBtn`).addEventListener("click", async () => {
      try{
        const lines = textEl.value.split("\n").map(v => v.trim()).filter(Boolean);
        if(!lines.length) throw new Error("沒有內容可記錄");
        // store identical lines as corrections, and if OCR text changed, keep it as manual correction input later
        for(const line of lines){
          await postJson("/api/save_correction", {wrong_text: line, correct_text: line});
        }
        toast("已記錄 AI 修正");
      }catch(err){ toast(err.message); }
    });

    await renderOrderCommon(mode);
  }

  async function renderOrderCommon(mode){
    try{
      const data = await api("/api/customers");
      state.customers = data.customers || [];
      // create general dropdown suggestions? keep current.
      if(mode === "master_orders"){
        // hide customer label visually if needed
      }
    }catch(e){}
  }

  function parseTextToItems(text){
    const lines = String(text || "").split("\n").map(s => s.trim()).filter(Boolean);
    return lines.map(line => {
      const clean = line.replace(/\s+/g, "");
      const m = clean.match(/(.+?)[=:](\d+)$/) || clean.match(/(.+?)x(\d+)$/i) || clean.match(/(.+?)\*(\d+)$/);
      if(m){
        return {product: m[1], quantity: Number(m[2])};
      }
      const m2 = clean.match(/(.+?)\s+(\d+)$/);
      if(m2) return {product: m2[1], quantity: Number(m2[2])};
      return {product: clean, quantity: 1};
    });
  }

  async function renderShipping(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>出貨</h3>
            <div class="muted">先扣總單，再扣訂單，最後扣庫存，自動回滾。</div>
          </div>
        </div>
        ${fileUploaderHtml("shipping")}
        <div class="grid cols-2">
          <div>
            <label>客戶名稱</label>
            <input id="shippingCustomer" placeholder="輸入客戶名稱">
            <div id="shippingCustomerSuggest" class="chips" style="margin-top:10px"></div>
          </div>
          <div>
            <label>出貨確認提示</label>
            <div class="card">按確認前會再次提醒，避免誤出貨。</div>
          </div>
        </div>
        <label>OCR 文字框（可人工修改）</label>
        <textarea id="shippingOcrText"></textarea>
        <div class="upload-meta">
          <span id="shippingWarning" class="confidence-chip">尚未辨識</span>
        </div>
        <div class="grid cols-2" style="margin-top:14px">
          <button class="btn primary" id="shippingConfirmBtn">確認出貨</button>
          <button class="btn secondary" id="shippingSaveCorrectionBtn">記錄 AI 修正</button>
        </div>
        <div class="hr"></div>
        <div id="shippingResult"></div>
      </section>
    `;
    bindUploadButtons("shipping");
    const customerEl = $("#shippingCustomer");
    const suggestEl = $("#shippingCustomerSuggest");
    const textEl = $("#shippingOcrText");
    customerEl.addEventListener("input", async () => {
      const q = customerEl.value.trim();
      if(!q){ suggestEl.innerHTML = ""; return; }
      const data = await api(`/api/customers/suggest?q=${encodeURIComponent(q)}`);
      suggestEl.innerHTML = (data.customers || []).map(c => `<button class="chip" data-name="${escapeHtml(c.name)}">${escapeHtml(c.name)}</button>`).join("");
    });
    suggestEl.addEventListener("click", e => {
      const btn = e.target.closest("button[data-name]");
      if(!btn) return;
      customerEl.value = btn.dataset.name;
      suggestEl.innerHTML = "";
    });
    $("#shippingConfirmBtn").addEventListener("click", async () => {
      if(!confirm("確認要出貨嗎？")) return;
      try{
        const items = parseTextToItems(textEl.value);
        const customer_name = customerEl.value.trim();
        const data = await postJson("/api/ship", {customer_name, items});
        $("#shippingResult").innerHTML = `
          <div class="card">
            <strong>出貨完成</strong>
            <div class="meta">客戶：${escapeHtml(data.customer || "")}</div>
            <div class="detail-list" style="margin-top:10px">
              ${(data.details || []).map(d => `<div class="detail-item">${escapeHtml(d.product)} × ${d.qty}｜總單 ${d.master}｜訂單 ${d.order}｜庫存 ${d.inventory}</div>`).join("")}
            </div>
          </div>`;
        toast("已完成出貨");
        await pollNotifications();
      }catch(err){ toast(err.message); }
    });
    $("#shippingSaveCorrectionBtn").addEventListener("click", async () => {
      const lines = textEl.value.split("\n").map(v => v.trim()).filter(Boolean);
      for(const line of lines){
        await postJson("/api/save_correction", {wrong_text: line, correct_text: line});
      }
      toast("已記錄 AI 修正");
    });
  }

  async function renderShippingRecords(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>出貨查詢</h3>
            <div class="muted">可選 3 / 7 / 10 / 15 天內資料。</div>
          </div>
          <div class="search-row">
            <select id="recordDays">
              <option value="">全部</option>
              <option value="3">3 天</option>
              <option value="7">7 天</option>
              <option value="10">10 天</option>
              <option value="15">15 天</option>
            </select>
            <button class="btn secondary" id="recordRefresh">查詢</button>
          </div>
        </div>
        <div id="recordsRoot"></div>
      </section>
    `;
    const load = async () => {
      const days = $("#recordDays").value;
      const data = await api(`/api/shipping_records${days ? `?days=${encodeURIComponent(days)}` : ""}`);
      const rows = data.records || [];
      $("#recordsRoot").innerHTML = rows.length ? `
        <table class="table">
          <thead><tr><th>客戶</th><th>商品</th><th>數量</th><th>操作人員</th><th>時間</th></tr></thead>
          <tbody>
            ${rows.map(r => `
              <tr>
                <td>${escapeHtml(r.customer_name || "")}</td>
                <td>${escapeHtml(r.product || "")}</td>
                <td>${r.qty || 0}</td>
                <td>${escapeHtml(r.operator || "")}</td>
                <td>${escapeHtml(r.shipped_at || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      ` : '<div class="muted">沒有資料</div>';
    };
    $("#recordRefresh").addEventListener("click", load);
    $("#recordDays").addEventListener("change", load);
    await load();
  }

  function buildWarehouseGrid(zone, cells){
    const grouped = {};
    (cells || []).forEach(c => {
      grouped[`${c.zone}-${c.column_no}-${c.position}-${c.slot_no}`] = c;
    });

    const all = [];
    for(let section = 1; section <= 6; section++){
      const cols = [];
      for(let col = 1; col <= 12; col++){
        cols.push(col);
      }
      all.push(`
        <div class="warehouse-section">
          <div class="section-number">${section}</div>
          ${cols.map(col => {
            const fronts = [];
            const backs = [];
            for(let slot=1; slot<=10; slot++){
              const f = grouped[`${zone}-${col}-front-${slot}`];
              const b = grouped[`${zone}-${col}-back-${slot}`];
              fronts.push(`<div class="slot ${f ? 'filled' : 'empty'} ${f && f.product && f.qty < 0 ? 'red':''}" data-cell='${encodeURIComponent(JSON.stringify({zone,column_no:col,position:"front",slot_no:slot}))}'>${f ? escapeHtml(f.product || f.customer_name || f.qty || "已錄入") : slot}</div>`);
              backs.push(`<div class="slot ${b ? 'filled' : 'empty'}" data-cell='${encodeURIComponent(JSON.stringify({zone,column_no:col,position:"back",slot_no:slot}))}'>${b ? escapeHtml(b.product || b.customer_name || b.qty || "已錄入") : slot}</div>`);
            }
            return `
              <div class="col-card" data-col="${col}">
                <div class="col-title">${col}欄</div>
                <div class="slot-row">
                  <div class="slot-label">前</div>
                  <div class="slot-grid">${fronts.join("")}</div>
                </div>
                <div class="slot-row" style="margin-top:8px">
                  <div class="slot-label">後</div>
                  <div class="slot-grid">${backs.join("")}</div>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      `);
    }
    return all.join("");
  }

  async function renderWarehouse(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>倉庫圖</h3>
            <div class="muted">A / B 區，點格子可編輯，可搜尋商品 / 客戶 / 格位。</div>
          </div>
          <div class="warehouse-switch">
            <button class="btn primary" id="zoneABtn">A倉</button>
            <button class="btn secondary" id="zoneBBtn">B倉</button>
            <button class="btn ghost" id="addColumnBtn">新增欄位</button>
          </div>
        </div>
        <div class="search-row">
          <input id="warehouseSearch" placeholder="搜尋商品 / 客戶 / 格位，輸入 113 直接跳出">
          <button class="btn secondary" id="warehouseSearchBtn">搜尋</button>
          <button class="btn secondary" id="warehouseRefreshBtn">重新整理</button>
        </div>
        <div class="muted small">點選已錄入格位可直接編輯，客戶名稱可輸入關鍵字自動補全完整名稱。</div>
        <div class="warehouse-scroll" style="margin-top:12px">
          <div id="warehouseRoot"></div>
        </div>
      </section>
    `;
    const warehouseRoot = $("#warehouseRoot");
    async function load(){
      const q = ($("#warehouseSearch").value || "").trim();
      const data = q ? await api(`/api/warehouse/search?q=${encodeURIComponent(q)}`) : await api(`/api/warehouse?zone=${encodeURIComponent(state.zone)}`);
      state.warehouseData = data.cells || [];
      warehouseRoot.innerHTML = buildWarehouseGrid(state.zone, state.warehouseData);
      bindWarehouseCellClicks();
    }
    $("#zoneABtn").addEventListener("click", async () => { state.zone="A"; await load(); });
    $("#zoneBBtn").addEventListener("click", async () => { state.zone="B"; await load(); });
    $("#warehouseSearchBtn").addEventListener("click", load);
    $("#warehouseRefreshBtn").addEventListener("click", load);

    $("#addColumnBtn").addEventListener("click", async () => {
      const col = prompt("新增欄位編號（1~12）或更多：", "13");
      if(!col) return;
      toast("欄位已規劃：請在格位編輯中直接使用該欄位");
    });

    await load();
    setInterval(load, 10000);
  }

  function bindWarehouseCellClicks(){
    $$(".slot[data-cell]").forEach(el => {
      el.addEventListener("click", () => {
        const data = JSON.parse(decodeURIComponent(el.dataset.cell));
        openWarehouseEditor(data);
      });
      el.addEventListener("dragstart", e => {
        e.dataTransfer.setData("application/json", JSON.stringify(JSON.parse(decodeURIComponent(el.dataset.cell))));
      });
      el.setAttribute("draggable", "true");
      el.addEventListener("dragover", e => e.preventDefault());
      el.addEventListener("drop", async e => {
        e.preventDefault();
        const src = JSON.parse(e.dataTransfer.getData("application/json"));
        const dst = JSON.parse(decodeURIComponent(el.dataset.cell));
        await postJson("/api/warehouse/save", {
          zone: dst.zone,
          column_no: dst.column_no,
          position: dst.position,
          slot_no: dst.slot_no,
          customer_name: src.customer_name || "",
          product: src.product || "",
          qty: src.qty || 0,
          note: src.note || ""
        });
        toast("已拖曳移動");
        await renderWarehouse();
      });
    });
  }

  async function openWarehouseEditor(data){
    const suggestions = (state.customers || []).map(c => c.name);
    const existingProducts = (state.inventory || []).map(i => i.product);
    const html = `
      <div class="modal-card modal-wide" style="display:block">
        <button class="modal-close" data-close="#editModal">×</button>
        <h3>格位編輯</h3>
        <div class="muted">${escapeHtml(data.zone)}區 / 第${data.column_no}欄 / ${data.position === 'front' ? '前' : '後'} / ${data.slot_no}</div>
        <div class="grid cols-2" style="margin-top:12px">
          <div>
            <label>客戶名稱</label>
            <input id="whCustomer" placeholder="打關鍵字搜尋完整客戶名">
            <div id="whCustomerSuggest" class="chips" style="margin-top:10px"></div>
          </div>
          <div>
            <label>商品</label>
            <input id="whProduct" placeholder="例如 113*12*05=122*3">
            <div id="whProductSuggest" class="chips" style="margin-top:10px"></div>
          </div>
        </div>
        <div class="grid cols-2">
          <div>
            <label>數量</label>
            <input id="whQty" type="number" value="1">
          </div>
          <div>
            <label>備註</label>
            <input id="whNote" placeholder="可留空">
          </div>
        </div>
        <div class="inline-actions" style="margin-top:14px">
          <button class="btn primary" id="whSaveBtn">儲存格位</button>
          <button class="btn secondary" id="whClearBtn">清除格位</button>
        </div>
        <div class="hr"></div>
        <div class="muted small">已錄入商品可下拉選擇；輸入 113 會直接顯示相關商品。</div>
      </div>
    `;
    $("#editModalContent").innerHTML = html;
    openModal("#editModal");
    const cust = $("#whCustomer");
    const prod = $("#whProduct");
    const qty = $("#whQty");
    const note = $("#whNote");
    const suggestCust = $("#whCustomerSuggest");
    const suggestProd = $("#whProductSuggest");

    cust.addEventListener("input", async () => {
      const q = cust.value.trim();
      if(!q){ suggestCust.innerHTML = ""; return; }
      const data = await api(`/api/customers/suggest?q=${encodeURIComponent(q)}`);
      suggestCust.innerHTML = (data.customers || []).map(c => `<button class="chip" data-name="${escapeHtml(c.name)}">${escapeHtml(c.name)}</button>`).join("");
    });
    suggestCust.addEventListener("click", e => {
      const btn = e.target.closest("button[data-name]");
      if(!btn) return;
      cust.value = btn.dataset.name;
      suggestCust.innerHTML = "";
    });

    prod.addEventListener("input", async () => {
      const q = prod.value.trim();
      if(!q){ suggestProd.innerHTML = ""; return; }
      const data = await api("/api/inventory");
      const products = (data.items || []).filter(i => [i.product, i.location].join(" ").includes(q)).slice(0, 20);
      suggestProd.innerHTML = products.map(p => `<button class="chip" data-product="${escapeHtml(p.product)}">${escapeHtml(p.product)} <span class="badge">${p.quantity || 0}</span></button>`).join("") || '<div class="muted">沒有可加入的商品</div>';
    });
    suggestProd.addEventListener("click", e => {
      const btn = e.target.closest("button[data-product]");
      if(!btn) return;
      prod.value = btn.dataset.product;
      suggestProd.innerHTML = "";
    });

    $("#whSaveBtn").addEventListener("click", async () => {
      await postJson("/api/warehouse/save", {
        zone: data.zone,
        column_no: data.column_no,
        position: data.position,
        slot_no: data.slot_no,
        customer_name: cust.value.trim(),
        product: prod.value.trim(),
        qty: Number(qty.value || 1),
        note: note.value.trim()
      });
      toast("已儲存");
      closeModal("#editModal");
      await renderWarehouse();
    });
    $("#whClearBtn").addEventListener("click", async () => {
      await postJson("/api/warehouse/delete", {id: data.id || null});
      toast("已清除");
      closeModal("#editModal");
      await renderWarehouse();
    });
  }

  async function renderCustomers(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>客戶資料</h3>
            <div class="muted">沒有新增按鈕，客戶會由訂單 / 總單 / 庫存自動同步進來。</div>
          </div>
        </div>
        <div id="customersRoot">載入中...</div>
      </section>
    `;

    const load = async () => {
      const data = await api("/api/customers");
      state.customers = data.customers || [];
      const groups = {北區: [], 中區: [], 南區: [], 未分類: []};
      (state.customers || []).forEach(c => {
        (groups[c.zone || "未分類"] || groups["未分類"]).push(c);
      });
      $("#customersRoot").innerHTML = Object.entries(groups).map(([zone, list]) => `
        <div class="zone-group">
          <div class="zone-head">
            <h4>${zone}</h4>
            <div class="badge">${list.length}</div>
          </div>
          <div class="chips">
            ${list.map(c => `<button class="chip" data-edit-customer="${c.id}">${escapeHtml(c.name)}</button>`).join("") || '<div class="muted">尚無客戶</div>'}
          </div>
        </div>
      `).join("");
    };

    $("#customersRoot").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-edit-customer]");
      if(!btn) return;
      const id = btn.getAttribute("data-edit-customer");
      const data = await api("/api/customers");
      const c = (data.customers || []).find(x => String(x.id) === String(id));
      if(!c) return;
      const html = `
        <h3>編輯客戶</h3>
        <div class="grid cols-2">
          <div><label>客戶名稱</label><input id="custName" value="${escapeHtml(c.name)}"></div>
          <div><label>區域</label><select id="custZone"><option ${c.zone==="北區"?"selected":""}>北區</option><option ${c.zone==="中區"?"selected":""}>中區</option><option ${c.zone==="南區"?"selected":""}>南區</option><option ${c.zone==="未分類"?"selected":""}>未分類</option></select></div>
        </div>
        <div class="grid cols-2">
          <div><label>電話</label><input id="custPhone" value="${escapeHtml(c.phone || "")}"></div>
          <div><label>地址</label><input id="custAddr" value="${escapeHtml(c.address || "")}"></div>
        </div>
        <label>特殊要求</label>
        <textarea id="custNote">${escapeHtml(c.note || "")}</textarea>
        <div class="inline-actions" style="margin-top:14px">
          <button class="btn primary" id="custSaveBtn">儲存</button>
        </div>
      `;
      $("#editModalContent").innerHTML = html;
      openModal("#editModal");
      $("#custSaveBtn").addEventListener("click", async () => {
        await postJson(`/api/customers/${id}`, {
          name: $("#custName").value.trim(),
          zone: $("#custZone").value,
          phone: $("#custPhone").value.trim(),
          address: $("#custAddr").value.trim(),
          note: $("#custNote").value.trim(),
        });
        toast("已更新客戶");
        closeModal("#editModal");
        await load();
      });
    });

    await load();
    setInterval(load, 12000);
  }

  async function renderTodayChanges(){
    const root = $("#moduleRoot");
    root.innerHTML = `
      <section class="section">
        <div class="top-bar">
          <div>
            <h3>今日異動</h3>
            <div class="muted">新增、出貨、未上架、異常一目了然。</div>
          </div>
          <div class="inline-actions">
            <button class="btn primary" id="refreshToday">重新整理</button>
          </div>
        </div>
        <div id="todayRoot">載入中...</div>
      </section>
    `;
    const load = async () => {
      const data = await api("/api/today_changes");
      const s = data.summary || {};
      const logs = data.logs || [];
      const notifications = data.notifications || [];
      $("#todayRoot").innerHTML = `
        <section class="summary-grid" style="margin-top:0">
          <div class="summary-card"><span>今日新增</span><strong>${s.new_count || 0}</strong></div>
          <div class="summary-card"><span>今日出貨量</span><strong>${s.ship_count || 0}</strong></div>
          <div class="summary-card"><span>未上架商品</span><strong>${s.unplaced_count || 0}</strong></div>
          <div class="summary-card"><span>異常紀錄</span><strong>${s.anomaly_count || 0}</strong></div>
        </section>
        <div class="hr"></div>
        <h4>通知列表</h4>
        <div class="detail-list">
          ${notifications.map(n => `
            <div class="detail-item">
              <div><strong>${escapeHtml(n.username || "系統")}</strong>｜${escapeHtml(n.message || "")}</div>
              <div class="meta">${escapeHtml(n.created_at || "")}｜${escapeHtml(n.kind || "")}</div>
            </div>
          `).join("") || '<div class="muted">沒有通知</div>'}
        </div>
        <div class="hr"></div>
        <h4>操作歷史</h4>
        <div class="detail-list">
          ${logs.map(log => `
            <div class="detail-item">
              <div><strong>${escapeHtml(log.username || "")}</strong>｜${escapeHtml(log.action || "")}</div>
              <div class="meta">${escapeHtml(log.created_at || "")}｜${escapeHtml(log.target_type || "")} ${escapeHtml(log.target_name || "")}</div>
            </div>
          `).join("") || '<div class="muted">沒有操作紀錄</div>'}
        </div>
      `;
    };
    $("#refreshToday").addEventListener("click", load);
    await load();
    setInterval(load, 10000);
  }

  // init
  document.addEventListener("DOMContentLoaded", async () => {
    wireCommon();

    if(window.APP_BOOT?.page === "home"){
      renderHomeExtras();
    }

    if(window.APP_BOOT?.page === "module"){
      await initModule();
    }

    // login page logic
    const loginForm = $("#loginForm");
    if(loginForm){
      const username = $("#username");
      const password = $("#password");
      const error = $("#loginError");
      const savedUser = localStorage.getItem("username");
      const savedPass = localStorage.getItem("password");
      if(savedUser) username.value = savedUser;
      if(savedPass) password.value = savedPass;
      loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        error.textContent = "";
        try{
          const res = await postJson("/api/login", {username: username.value.trim(), password: password.value.trim()});
          localStorage.setItem("username", username.value.trim());
          localStorage.setItem("password", password.value.trim());
          window.location.href = res.redirect || "/";
        }catch(err){
          error.textContent = err.message;
        }
      });
    }

    // Home badge click / notifications
    if(window.APP_BOOT?.page === "home"){
      const badge = Number(window.APP_BOOT.badge || 0);
      refreshBadge(badge);
    }
  });

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    window.deferredPrompt = e;
  });

  if("serviceWorker" in navigator){
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
    });
  }
})();
