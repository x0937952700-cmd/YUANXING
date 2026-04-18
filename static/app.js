// ===== 全域 =====
let activityData = []
let unreadCount = 0

// ===== Toast =====
function showToast(text, type="ok"){
  let t = document.createElement("div")
  t.className = "toast show " + type
  t.innerText = text
  document.body.appendChild(t)

  setTimeout(()=>{
    t.classList.remove("show")
    setTimeout(()=>t.remove(),200)
  },2500)
}

// ===== OCR =====
async function handleOCR(file){
  let text = "（辨識失敗，可手動輸入）"

  try{
    let form = new FormData()
    form.append("file", file)

    let res = await fetch("/ocr",{method:"POST",body:form})
    let data = await res.json()

    if(data.text && data.text.trim() !== ""){
      text = data.text
    }

    document.getElementById("ocr-text").value = text
    document.getElementById("ocr-confidence-pill").innerText =
      (data.confidence || 0) + "%"

  }catch(e){
    document.getElementById("ocr-text").value = text
  }
}

// ===== 上傳 =====
function openAlbumPicker(){
  document.getElementById("album-input").click()
}
function openCameraPicker(){
  document.getElementById("camera-input").click()
}

document.getElementById("album-input")?.addEventListener("change",e=>{
  if(e.target.files[0]) handleOCR(e.target.files[0])
})
document.getElementById("camera-input")?.addEventListener("change",e=>{
  if(e.target.files[0]) handleOCR(e.target.files[0])
})

// ===== 提交 =====
async function confirmSubmit(){
  let text = document.getElementById("ocr-text").value

  await fetch("/submit",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text})
  })

  showToast("已送出","ok")
  addActivity("你","新增資料")
}

// ===== 今日異動 =====
function addActivity(user,action){
  let time = new Date().toLocaleTimeString()

  activityData.unshift({user,action,time})
  unreadCount++

  updateBadge()
  renderActivity()
}

function updateBadge(){
  let b = document.getElementById("activity-badge")
  if(!b) return

  if(unreadCount>0){
    b.classList.remove("hidden")
    b.innerText = unreadCount
  }else{
    b.classList.add("hidden")
  }
}

function renderActivity(){
  let box = document.getElementById("activity-feed")
  if(!box) return

  box.innerHTML = ""

  activityData.forEach((a,i)=>{
    let row = document.createElement("div")
    row.className = "activity-row"
    row.innerHTML = `
      <div class="activity-left">
        <div class="activity-user">${a.user}</div>
        <div class="activity-time">${a.time}</div>
      </div>
      <div class="activity-action">${a.action}</div>
    `

    // 滑動刪除
    let startX = 0
    row.addEventListener("touchstart",e=>{
      startX = e.touches[0].clientX
    })

    row.addEventListener("touchmove",e=>{
      let moveX = e.touches[0].clientX
      if(startX - moveX > 30){
        row.classList.add("swiping")
      }
    })

    row.addEventListener("touchend",e=>{
      let endX = e.changedTouches[0].clientX
      if(startX - endX > 80){
        row.classList.add("deleted")
        setTimeout(()=>{
          activityData.splice(i,1)
          renderActivity()
        },200)
      }else{
        row.classList.remove("swiping")
      }
    })

    box.appendChild(row)
  })
}

// ===== 點進今日異動清除紅點 =====
if(location.pathname.includes("activity")){
  unreadCount = 0
  setTimeout(updateBadge,300)
}

// ===== 倉庫搜尋 =====
function searchWarehouse(){
  let val = document.getElementById("warehouse-search")?.value || ""
  let resultBox = document.getElementById("warehouse-search-results")

  if(!resultBox) return

  resultBox.innerHTML = ""
  resultBox.classList.remove("hidden")

  // 模擬資料
  let mock = [
    {name:"113*6",loc:"A1"},
    {name:"120*3",loc:"B2"}
  ]

  let filtered = mock.filter(i=>i.name.includes(val))

  filtered.forEach(i=>{
    let d = document.createElement("div")
    d.className = "search-card"
    d.innerText = i.name + " → " + i.loc
    resultBox.appendChild(d)
  })
}

function clearWarehouseSearch(){
  let box = document.getElementById("warehouse-search-results")
  if(box){
    box.innerHTML=""
    box.classList.add("hidden")
  }
}

// ===== 自動同步 =====
setInterval(()=>{
  fetch("/sync")
  .then(r=>r.json())
  .then(data=>{
    // 可接庫存/倉庫刷新
  })
},5000)