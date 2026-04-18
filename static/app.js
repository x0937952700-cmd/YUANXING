async function logout(){await fetch('/api/logout',{method:'POST'});location='/login'}
async function loadSummary(){const r=await fetch('/api/activity/summary'); if(!r.ok) return; const j=await r.json(); if(!j.success) return; const s=j.summary||{}; const badge=document.getElementById('badge'); const inline=document.getElementById('summary-inline'); if(badge){badge.textContent=s.unread||0; badge.style.display=(s.unread||0)>0?'inline-flex':'none';} if(inline){inline.textContent=`新增 ${s.today_new||0}｜出貨 ${s.today_shipping_qty||0}｜未錄入倉庫圖 ${s.unplaced_qty||0}`;}}
if(location.pathname==='/' ){loadSummary();}
if('serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('/service-worker.js').catch(()=>{});});}
const root=document.getElementById('app');
if(root){
  const m=root.dataset.module;
  if(m==='inventory') renderInventory();
  if(m==='orders') renderOrders();
  if(m==='master_order') renderMasterOrders();
  if(m==='ship') renderShip();
  if(m==='warehouse') renderWarehouse();
  if(m==='customers') renderCustomers();
  if(m==='activity') renderActivity();
}
function card(html){return `<div class="card">${html}</div>`}
async function renderInventory(){const r=await fetch('/api/inventory'); const j=await r.json(); const items=j.items||[]; root.innerHTML=card(`<h3>庫存</h3><p>未錄入倉庫圖會標紅</p><div>${items.map(x=>`<div class="list-row ${x.needs_red?'danger':''}"><div><b>${x.product_text}</b> ${x.qty}件</div><div>${x.location||'未指定'} / 未錄入:${x.unplaced_qty||0}</div></div>`).join('')}</div><hr><h4>OCR 上傳</h4><input id="ocrFile" type="file" accept="image/*"><button onclick="uploadOCR()">辨識</button><div id="ocrResult"></div>`)}
async function uploadOCR(){const f=document.getElementById('ocrFile').files[0]; if(!f) return; const fd=new FormData(); fd.append('file',f); const r=await fetch('/api/upload_ocr',{method:'POST',body:fd}); const j=await r.json(); document.getElementById('ocrResult').innerHTML=`<pre>${j.text||''}</pre><div>信心值: ${j.confidence||0}</div><div>${j.warning||''}</div><div>${(j.hints||[]).join('<br>')}</div>`;}
async function renderOrders(){const r=await fetch('/api/orders'); const j=await r.json(); root.innerHTML=card(`<h3>訂單</h3>${(j.items||[]).map(x=>`<div class="list-row"><div><b>${x.customer_name}</b> - ${x.product_text}</div><div>${x.qty}</div></div>`).join('')}`)}
async function renderMasterOrders(){const r=await fetch('/api/master_orders'); const j=await r.json(); root.innerHTML=card(`<h3>總單</h3><p>新邏輯：不顯示客戶名稱</p>${(j.items||[]).map(x=>`<div class="list-row"><div><b>${x.product_text}</b></div><div>${x.qty}</div></div>`).join('')}`)}
async function renderShip(){root.innerHTML=card('<h3>出貨</h3><p>可沿用既有 API。</p>')}
async function renderCustomers(){const r=await fetch('/api/customers'); const j=await r.json(); root.innerHTML=card(`<h3>客戶資料</h3>${(j.items||[]).map(x=>`<div class="list-row"><div><b>${x.name}</b></div><div>${x.region||''}</div></div>`).join('')}`)}
async function renderActivity(){const mark=localStorage.getItem('activity_seen_at')||''; const r=await fetch('/api/activity/feed'); const j=await r.json(); localStorage.setItem('activity_seen_at', new Date().toISOString().slice(0,19).replace('T',' ')); root.innerHTML=card(`<h3>今日異動</h3><div class="stats"><div>新增 ${j.summary?.today_new||0}</div><div>出貨量 ${j.summary?.today_shipping_qty||0}</div><div>未錄入倉庫圖 ${j.summary?.unplaced_qty||0}</div></div>${(j.items||[]).map(x=>`<div class="list-row swipe-delete"><div>${x.action}</div><div>${x.created_at}</div></div>`).join('')}`); const badge=document.getElementById('badge'); if(badge){badge.textContent='0'; badge.style.display='none';}}
async function renderWarehouse(){const r=await fetch('/api/warehouse'); const j=await r.json(); const cells=j.cells||[]; root.innerHTML=card(`<h3>倉庫圖</h3><p>A/B 區直式結構</p><div class="warehouse-grid">${cells.map(c=>`<div class="cell ${JSON.parse(c.items_json||'[]').length?'used':'empty'}"><span>${c.zone}${c.column_index}-${c.slot_type[0].toUpperCase()}${c.slot_number}</span></div>`).join('')}</div>`)}
