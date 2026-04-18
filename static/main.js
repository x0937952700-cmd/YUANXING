let draggingProduct = null

// ===== 每2秒同步 =====
setInterval(loadWarehouse,2000)

// ===== 載入倉庫 =====
async function loadWarehouse(){
  const r = await fetch('/api/w')
  const data = await r.json()

  const map = {}
  data.forEach(i=>{
    map[i[2]] = i[0] // location -> product
  })

  let html = '<div class="grid">'

  for(let i=1;i<=30;i++){
    const loc = "A-"+i
    const p = map[loc] || ""

    html += `
    <div class="cell ${p?'used':'empty'}"
         ondragover="allowDrop(event)"
         ondrop="drop('${loc}')">

         <div class="loc">${loc}</div>

         <div draggable="true"
              ondragstart="drag('${p}')"
              class="item">
              ${p || ''}
         </div>
    </div>`
  }

  html += '</div>'

  document.getElementById("app").innerHTML = html
}

// ===== 拖 =====
function drag(p){
  draggingProduct = p
}

// ===== 放 =====
async function drop(loc){
  if(!draggingProduct) return

  await fetch('/api/move',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      p: draggingProduct,
      l: loc
    })
  })

  draggingProduct = null
  loadWarehouse()
}

// ===== 允許拖 =====
function allowDrop(e){
  e.preventDefault()
}