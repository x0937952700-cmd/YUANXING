
const socket = io();
let badge = 0;

socket.on("update", ()=>{
    refreshActivity();
    badge++;
    updateBadge();
});

function updateBadge(){
    const b=document.getElementById("today-badge");
    if(!b) return;
    b.innerText=badge;
}

async function refreshActivity(){
    const r=await fetch("/api/activity");
    const d=await r.json();
    const el=document.getElementById("activity-list");
    if(!el) return;
    el.innerHTML="";
    d.forEach(i=>{
        let div=document.createElement("div");
        div.innerText=i.action;
        el.appendChild(div);
    });
}

async function searchWarehouse(q){
    const r=await fetch("/api/search?q="+q);
    const d=await r.json();
    document.querySelectorAll("[data-slot]").forEach(el=>el.style.outline="");
    Object.keys(d).forEach(s=>{
        let el=document.querySelector(`[data-slot='${s}']`);
        if(el) el.style.outline="3px solid yellow";
    });
}

let dragItem=null;
function onDragStart(item){dragItem=item;}

async function onDrop(slot){
    if(!dragItem) return;
    await fetch("/api/warehouse/place",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({slot,item:dragItem})
    });
    dragItem=null;
}

function applyWarehouseColors(){
    document.querySelectorAll("[data-slot]").forEach(el=>{
        const t=el.innerText;
        if(!t) el.style.background="#eee";
        else el.style.background="#a5d6a7";
    });
}
