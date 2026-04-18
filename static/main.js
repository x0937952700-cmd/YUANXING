
    async function addInventory(){
        const text=document.getElementById("batch").value;
        await fetch("/inventory",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:"batch="+encodeURIComponent(text)});
    }

    async function placeItem(slot,item){
        await fetch("/place",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:`slot=${slot}&item=${item}`});
    }

    async function searchItem(q){
        const res=await fetch("/search?q="+q);
        console.log(await res.json());
    }

    function render(){
        const el=document.getElementById("warehouse");
        if(!el)return;
        el.innerHTML="";
        for(let i=1;i<=10;i++){
            let d=document.createElement("div");
            d.innerHTML="[格 "+i+"]";
            d.onclick=()=>placeItem(i,"貨物");
            el.appendChild(d);
        }
    }

    render();

    const socket=io();
    socket.on("update",()=>location.reload());
    