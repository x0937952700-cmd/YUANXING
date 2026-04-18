async function renderWarehouse(){
  const r = await fetch('/api/w');
  const data = await r.json();

  let html = '<div class="grid">';

  data.forEach(i=>{
    html += `<div class="cell ${i[2]?'used':'empty'}"
      draggable="true"
      ondragstart="drag(event,'${i[0]}')"
      onclick="focusItem('${i[0]}')">
      ${i[0]}<br>${i[2]||'未放置'}
    </div>`;
  });

  html+='</div>';
  document.getElementById('app').innerHTML=html;
}

function drag(ev,p){
  ev.dataTransfer.setData("p",p);
}

async function drop(loc){
  const p = event.dataTransfer.getData("p");

  await fetch('/api/move',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:p,l:loc})
  });

  renderWarehouse();
}

async function focusItem(p){
  const cells = document.querySelectorAll('.cell');
  cells.forEach(c=>c.classList.remove('highlight'));

  const target = [...cells].find(c=>c.innerText.includes(p));
  if(target){
    target.classList.add('highlight');

    let i=0;
    const t=setInterval(()=>{
      target.classList.toggle('blink');
      if(i++>5) clearInterval(t);
    },300);
  }
}