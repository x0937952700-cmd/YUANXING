// =============================
// 🔥 全域狀態
// =============================
let currentPage = ''
let draggingProduct = null

// =============================
// 🔥 自動即時同步（企業版）
// =============================
setInterval(()=>{
  if(currentPage==='inventory') loadInventory()
  if(currentPage==='warehouse') loadWarehouse()
  if(currentPage==='activity') loadActivity()
},2000)


// =============================
// 🔥 通知（企業版）
// =============================
function toast(msg){
  const t=document.createElement('div')
  t.innerText=msg
  t.style=`
    position:fixed;
    top:20px;
    right:20px;
    background:#333;
    color:#fff;
    padding:10px 15px;
    border-radius:8px;
    z-index:9999;
  `
  document.body.appendChild(t)
  setTimeout(()=>t.remove(),2000)
}


// =============================
// 🔥 OCR → 點擊定位（企業核心）
// =============================
function highlightProduct(product){

  document.querySelectorAll('.cell').forEach(c=>{
    c.style.outline = 'none'

    if(c.innerText.includes(product)){
      c.style.outline = '3px solid red'

      c.scrollIntoView({
        behavior:'smooth',
        block:'center'
      })
    }
  })
}


// =============================
// 🔥 OCR 上傳
// =============================
async function uploadOCR(){

  const f=document.getElementById('ocrFile').files[0]
  if(!f) return

  const fd=new FormData()
  fd.append('file',f)

  const r=await fetch('/api/upload_ocr',{method:'POST',body:fd})
  const j=await r.json()

  const lines = j.lines || []

  document.getElementById('ocrResult').innerHTML =
    `<div>信心值: ${j.confidence||0}</div>` +
    lines.map(l=>
      `<div onclick="highlightProduct('${l}')"
            style="padding:5px;border-bottom:1px solid #ddd;">
        ${l}
      </div>`
    ).join('')

  toast("OCR完成")
}


// =============================
// 🔥 庫存
// =============================
async function loadInventory(){

  const r=await fetch('/api/inventory')
  const j=await r.json()

  const items = j.items || []

  document.getElementById("app").innerHTML =
    `<h3>庫存</h3>` +
    items.map(x=>
      `<div class="list-row">
        <b>${x.p}</b> ${x.q}
      </div>`
    ).join('')
}


// =============================
// 🔥 訂單
// =============================
async function createOrder(){

  const p=document.getElementById("order_p").value
  const q=parseInt(document.getElementById("order_q").value)

  const r=await fetch('/api/order',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p,q})
  })

  const j=await r.json()

  if(j.error){
    toast(j.error)
  }else{
    toast("訂單成功")
  }
}


// =============================
// 🔥 出貨
// =============================
async function ship(){

  const p=document.getElementById("ship_p").value
  const q=parseInt(document.getElementById("ship_q").value)

  const r=await fetch('/api/ship',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p,q})
  })

  const j=await r.json()

  if(j.error){
    toast(j.error)
  }else{
    toast("出貨成功")
  }
}


// =============================
// 🔥 倉庫（拖拉 + 即時）
// =============================
async function loadWarehouse(){

  currentPage = 'warehouse'

  const r = await fetch('/api/w')
  const data = await r.json()

  const map = {}
  data.forEach(i=>{
    map[i[2]] = i[0]
  })

  let html = '<h3>倉庫圖</h3><div class="grid">'

  for(let i=1;i<=30;i++){
    const loc = "A-"+i
    const p = map[loc] || ""

    html += `
    <div class="cell ${p?'used':'empty'}"
         data-loc="${loc}">

         <div class="loc">${loc}</div>

         <div class="item"
              draggable="true"
              data-product="${p}">
              ${p || ''}
         </div>
    </div>`
  }

  html += '</div>'

  document.getElementById("app").innerHTML = html

  enableWarehouseDrag()
}


// =============================
// 🔥 拖拉系統（企業版）
// =============================
function enableWarehouseDrag(){

  document.querySelectorAll('.cell').forEach(cell=>{
    cell.ondragover = e => e.preventDefault()

    cell.ondrop = async ()=>{
      if(!draggingProduct) return

      await fetch('/api/move',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          p: draggingProduct,
          l: cell.dataset.loc
        })
      })

      toast("已移動")

      draggingProduct = null
      loadWarehouse()
    }
  })

  document.querySelectorAll('.item').forEach(el=>{
    el.ondragstart = ()=>{
      draggingProduct = el.dataset.product
    }
  })
}


// =============================
// 🔥 異動
// =============================
async function loadActivity(){

  currentPage = 'activity'

  const r=await fetch('/api/activity')
  const j=await r.json()

  const items = j.items || []

  document.getElementById("app").innerHTML =
    `<h3>異動紀錄</h3>` +
    items.map(x=>
      `<div>${x.a||x.action} ${x.t||x.created_at}</div>`
    ).join('')
}