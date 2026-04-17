const state = {
  mode: "inventory",
  currentUser: "",
  currentConfidence: 0,
  originalText: "",
  originalLines: [],
  highlightedLocations: [],
  currentList: "inventoryList"
};

const customerGroups = {
  "北區": ["保固", "德馨", "龍興"],
  "中區": ["三美"],
  "南區": ["揚舜", "國翔"]
};

function $(id){ return document.getElementById(id); }

async function api(url, options = {}){
  const res = await fetch(url, options);
  const data = await res.json();
  return data;
}

function parseLine(line){
  const raw = (line || "").trim();
  if(!raw) return null;

  const separators = ["=", "x", "X", "＊", "*", ":"];
  for(const sep of separators){
    const idx = raw.lastIndexOf(sep);
    if(idx > 0){
      const left = raw.slice(0, idx).trim();
      const right = raw.slice(idx + 1).trim();
      if(left && /^\d+$/.test(right)){
        return { product: left, quantity: parseInt(right, 10) };
      }
    }
  }

  const parts = raw.split(/\s+/);
  if(parts.length >= 2 && /^\d+$/.test(parts[parts.length - 1])){
    return {
      product: parts.slice(0, -1).join(" ").trim(),
      quantity: parseInt(parts[parts.length - 1], 10)
    };
  }

  return { product: raw, quantity: 1 };
}

function parseTextareaToItems(text){
  const lines = (text || "").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const items = [];
  for(const line of lines){
    const parsed = parseLine(line);
    if(parsed && parsed.product && parsed.quantity > 0){
      items.push({
        product: parsed.product,
        quantity: parsed.quantity,
        location: $("locationInput").value.trim()
      });
    }
  }
  return { lines, items };
}

function setMode(mode){
  state.mode = mode;
  document.querySelectorAll(".nav-btn, .big-menu-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  const labels = {
    inventory: "庫存",
    order: "訂單",
    master: "總單",
    ship: "出貨",
    shipping: "出貨查詢",
    warehouse: "倉庫圖"
  };

  $("modeLabel").innerText = labels[mode] || mode;

  const hint = {
    inventory: "庫存模式：OCR 後可直接建立商品與格位。",
    order: "訂單模式：填客戶名稱後建立 pending 訂單。",
    master: "總單模式：同客戶同商品自動合併累加。",
    ship: "出貨模式：先扣總單，再扣訂單，最後扣庫存。",
    shipping: "出貨查詢：查看歷史出貨紀錄。",
    warehouse: "倉庫圖：反查格位與高亮商品位置。"
  };

  $("ocrHint").innerText = hint[mode] || "";
  renderModeUI();
}

function renderCustomerGroups(){
  const wrap = $("customerGroups");
  wrap.innerHTML = "";
  for(const [group, customers] of Object.entries(customerGroups)){
    const box = document.createElement("div");
    box.className = "group";
    box.innerHTML = `<div class="group-title">${group}</div>`;
    const items = document.createElement("div");
    items.className = "group-items";
    customers.forEach(name => {
      const btn = document.createElement("button");
      btn.className = "tag-btn";
      btn.innerText = name;
      btn.onclick = () => {
        $("customerInput").value = name;
        setMode("order");
      };
      items.appendChild(btn);
    });
    box.appendChild(items);
    wrap.appendChild(box);
  }
}

function zoneNameFromLocation(location){
  const loc = (location || "").trim();
  if(!loc) return "未指定";
  if(/^A/i.test(loc)) return "A倉";
  if(/^B/i.test(loc)) return "B倉";
  if(/^C/i.test(loc)) return "C倉";
  if(/前排/.test(loc)) return "前排";
  if(/中排/.test(loc)) return "中排";
  if(/後排/.test(loc)) return "後排";
  return "其他";
}

function renderWarehouse(items = []){
  const el = $("warehouseMap");
  el.innerHTML = "";

  const groups = {
    "前排": [],
    "中排": [],
    "後排": [],
    "其他": []
  };

  const highlightKeys = new Set(
    (items || []).map(x => `${(x.location || "").trim()}__${(x.product || "").trim()}`)
  );

  const inventory = state.inventoryCache || [];
  inventory.forEach(row => {
    const loc = (row.location || "").trim();
    const zone = zoneNameFromLocation(loc);
    groups[zone].push(row);
  });

  Object.entries(groups).forEach(([zone, rows]) => {
    const zoneEl = document.createElement("div");
    zoneEl.className = "warehouse-zone";
    zoneEl.innerHTML = `<h3>${zone}</h3>`;
    const list = document.createElement("div");
    list.className = "zone-items";

    if(rows.length === 0){
      const empty = document.createElement("div");
      empty.className = "zone-card";
      empty.innerText = "暫無資料";
      list.appendChild(empty);
    }else{
      rows.forEach(row => {
        const card = document.createElement("div");
        const key = `${(row.location || "").trim()}__${(row.product || "").trim()}`;
        card.className = "zone-card" + (highlightKeys.has(key) ? " highlight" : "");
        card.innerHTML = `<strong>${row.location || "未指定"}</strong>　${row.product || ""}<br>庫存：${row.quantity || 0}`;
        list.appendChild(card);
      });
    }

    zoneEl.appendChild(list);
    el.appendChild(zoneEl);
  });
}

function renderTable(tableId, rows, columns){
  const table = $(tableId);
  if(!rows || rows.length === 0){
    table.innerHTML = `<tr><th>無資料</th></tr>`;
    return;
  }

  const headers = columns || Object.keys(rows[0]);
  let html = "<thead><tr>";
  headers.forEach(h => { html += `<th>${h}</th>`; });
  html += "</tr></thead><tbody>";

  rows.forEach(row => {
    html += "<tr>";
    headers.forEach(h => {
      html += `<td>${escapeHtml(row[h] ?? "")}</td>`;
    });
    html += "</tr>";
  });

  html += "</tbody>";
  table.innerHTML = html;
}

function escapeHtml(value){
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshInventory(){
  const data = await api("/api/inventory/list");
  if(data.success){
    state.inventoryCache = data.items || [];
    const rows = (data.items || []).map(x => ({
      商品: x.product,
      數量: x.quantity,
      格位: x.location,
      操作人員: x.operator || "",
      更新時間: x.updated_at || ""
    }));
    renderTable("inventoryTable", rows, ["商品", "數量", "格位", "操作人員", "更新時間"]);
    if(state.mode === "warehouse"){
      renderWarehouse(state.highlightedLocations);
    } else {
      renderWarehouse(state.highlightedLocations);
    }
  }
}

async function refreshOrders(){
  const data = await api("/api/orders/list");
  if(data.success){
    state.orderCache = data.items || [];
  }
}

async function refreshMasterOrders(){
  const data = await api("/api/master_orders/list");
  if(data.success){
    state.masterCache = data.items || [];
  }
}

async function refreshShipping(){
  const data = await api("/api/shipping_records");
  if(data.success){
    const rows = (data.records || []).map(x => ({
      客戶: x.customer,
      商品: x.product,
      數量: x.qty,
      操作人員: x.operator || "",
      出貨時間: x.shipped_at || ""
    }));
    renderTable("shippingTable", rows, ["客戶", "商品", "數量", "操作人員", "出貨時間"]);
  }
}

async function refreshLogs(){
  const data = await api("/api/logs");
  if(data.success){
    const rows = (data.items || []).map(x => ({
      誰: x.username,
      時間: x.created_at,
      做什麼: x.action
    }));
    renderTable("logsTable", rows, ["誰", "時間", "做什麼"]);
  }
}

async function refreshBackups(){
  const data = await api("/api/backups");
  if(data.success){
    const rows = (data.files || []).map(x => ({
      備份資料夾: x.name,
      建立時間: x.created_at,
      大小: formatBytes(x.size || 0),
      路徑: x.path
    }));
    renderTable("backupsTable", rows, ["備份資料夾", "建立時間", "大小", "路徑"]);
  }
}

function formatBytes(bytes){
  if(bytes < 1024) return `${bytes} B`;
  if(bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function refreshSession(){
  const data = await api("/api/session");
  if(data.success && data.authenticated){
    state.currentUser = data.user || "";
    $("currentUser").innerText = state.currentUser || "未登入";
    return true;
  }
  window.location.href = "/login";
  return false;
}

function setWarning(text){
  $("warningBox").innerText = text || "正常";
}

function applyOcrResult(data){
  state.originalText = data.text || "";
  state.originalLines = (data.lines || []).slice();
  state.currentConfidence = data.confidence || 0;
  $("ocrText").value = data.text || "";
  $("confidenceLabel").innerText = state.currentConfidence;
  setWarning(data.warning || "正常");
  state.highlightedLocations = data.locations || [];
  renderWarehouse(state.highlightedLocations);

  if(state.currentConfidence < 80){
    setWarning(data.warning || "請確認辨識內容");
  }
}

async function compressImage(file){
  if(!file.type.startsWith("image/")) return file;

  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = function(ev){
      const img = new Image();
      img.onload = function(){
        const maxWidth = 1600;
        const ratio = Math.min(1, maxWidth / img.width);
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * ratio);
        canvas.height = Math.round(img.height * ratio);
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => {
          if(blob){
            resolve(new File([blob], "upload.jpg", { type: "image/jpeg" }));
          }else{
            resolve(file);
          }
        }, "image/jpeg", 0.82);
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  });
}

async function uploadOcr(file){
  const fd = new FormData();
  fd.append("file", await compressImage(file));

  setWarning("辨識中...");
  $("ocrHint").innerText = "辨識中，請稍候...";

  const res = await fetch("/api/upload_ocr", {
    method: "POST",
    body: fd
  });
  const data = await res.json();

  if(!data.success){
    setWarning(data.error || "OCR失敗");
    $("ocrHint").innerText = data.error || "OCR失敗";
    return;
  }

  applyOcrResult(data);
  $("ocrHint").innerText = "OCR完成，可人工修改後再送出。";
  await refreshInventory();
}

async function saveCorrectionsIfNeeded(before, after){
  const oldLines = (before || "").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const newLines = (after || "").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const count = Math.max(oldLines.length, newLines.length);

  for(let i = 0; i < count; i++){
    const oldLine = oldLines[i] || "";
    const newLine = newLines[i] || "";
    if(oldLine && newLine && oldLine !== newLine){
      await fetch("/api/save_correction", {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
          wrong_text: oldLine,
          correct_text: newLine
        })
      });
    }
  }
}

async function confirmSubmit(){
  const text = $("ocrText").value.trim();
  const customer = $("customerInput").value.trim();
  const location = $("locationInput").value.trim();

  const { lines, items } = parseTextareaToItems(text);
  if(items.length === 0){
    setWarning("沒有可送出的資料");
    return;
  }

  const payload = {
    text,
    items,
    customer,
    location
  };

  let url = "/api/inventory";
  if(state.mode === "order") url = "/api/order";
  if(state.mode === "master") url = "/api/master_order";
  if(state.mode === "ship") url = "/api/ship";

  if((state.mode === "order" || state.mode === "master" || state.mode === "ship") && !customer){
    setWarning("請先輸入客戶名稱");
    return;
  }

  if(state.mode === "ship"){
    const ok = confirm("確認要出貨嗎？會先扣總單，再扣訂單，最後扣庫存。");
    if(!ok) return;
  }

  const beforeText = state.originalText;
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  const data = await res.json();

  if(!data.success){
    setWarning(data.error || "送出失敗");
    return;
  }

  if(beforeText && text !== beforeText){
    await saveCorrectionsIfNeeded(beforeText, text);
  }

  setWarning("送出成功");
  $("ocrHint").innerText = "送出成功，可繼續上傳下一張。";
  await refreshAll();
}

async function findLocationsFromText(){
  const text = $("ocrText").value.trim();
  const { items } = parseTextareaToItems(text);
  if(items.length === 0){
    setWarning("沒有可反查的商品");
    return;
  }

  const res = await api("/api/find_locations", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ items })
  });

  if(res.success){
    state.highlightedLocations = res.items || [];
    renderWarehouse(state.highlightedLocations);
    setWarning("已反查商品位置");
  }
}

async function manualBackup(){
  const res = await api("/api/backup");
  if(res.success){
    setWarning("已建立備份");
    await refreshBackups();
  }else{
    setWarning(res.error || "備份失敗");
  }
}

async function refreshAll(){
  await Promise.all([
    refreshInventory(),
    refreshOrders(),
    refreshMasterOrders(),
    refreshShipping(),
    refreshLogs(),
    refreshBackups()
  ]);
}

function renderModeUI(){
  const labels = {
    inventory: "庫存：建立商品 / 格位 / 操作人員",
    order: "訂單：建立 pending 訂單",
    master: "總單：同客戶同商品合併累加",
    ship: "出貨：先扣總單，再扣訂單，最後扣庫存",
    shipping: "出貨查詢：查看歷史出貨紀錄",
    warehouse: "倉庫圖：高亮商品所在位置"
  };
  $("ocrHint").innerText = labels[state.mode] || "";
}

async function init(){
  const ok = await refreshSession();
  if(!ok) return;

  renderCustomerGroups();
  setMode("inventory");

  document.querySelectorAll(".nav-btn, .big-menu-btn").forEach(btn => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });

  document.querySelectorAll(".mini-tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".mini-tab").forEach(x => x.classList.remove("active"));
      btn.classList.add("active");
      state.currentList = btn.dataset.list;
      if(state.currentList === "inventoryList") await refreshInventory();
      if(state.currentList === "masterList") await refreshMasterOrders();
      if(state.currentList === "orderList") await refreshOrders();
    });
  });

  $("fileInput").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if(file){
      await uploadOcr(file);
      e.target.value = "";
    }
  });

  $("confirmBtn").addEventListener("click", confirmSubmit);
  $("findLocationBtn").addEventListener("click", findLocationsFromText);
  $("backupBtn").addEventListener("click", manualBackup);
  $("refreshBackupBtn").addEventListener("click", refreshBackups);
  $("refreshBtn").addEventListener("click", refreshAll);

  $("logoutBtn").addEventListener("click", async () => {
    await fetch("/api/logout", { method:"POST" });
    localStorage.removeItem("username");
    localStorage.removeItem("password");
    window.location.href = "/login";
  });

  await refreshAll();
  $("currentUser").innerText = state.currentUser || "未登入";
  renderWarehouse([]);
}

window.addEventListener("load", init);
