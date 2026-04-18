async function autoUpload(){

  const f = document.getElementById('file').files[0];
  if(!f) return alert("請選圖片");

  const fd = new FormData();
  fd.append("file", f);

  const r = await fetch('/api/auto_ocr',{
    method:'POST',
    body:fd
  });

  const j = await r.json();

  document.getElementById("result").innerHTML = `
    <h3>辨識結果</h3>
    <pre>${j.text}</pre>

    <h3>自動入庫</h3>
    ${j.result.map(x=>`
      <div>
        ${x.product} → ${x.qty}件 → 📍${x.location}
      </div>
    `).join("")}
  `;
}