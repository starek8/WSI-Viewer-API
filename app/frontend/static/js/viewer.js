const viewer = OpenSeadragon({
    id:"openseadragon",
    prefixUrl:"https://openseadragon.github.io/openseadragon/images/",
    tileSources:`/dzi/${slide_uuid}/${filename}`
});

document.getElementById("saveBtn").addEventListener("click", saveView);
document.getElementById("loadBtn").addEventListener("click", loadLastView);
document.getElementById("loadSelectedBtn").addEventListener("click", loadSelectedView);

async function saveView() {
    const vp = viewer.viewport;
    const viewState = {
        zoom: vp.getZoom(),
        center_x: vp.getCenter().x,
        center_y: vp.getCenter().y,
        rotation: vp.getRotation()
    };
    const canvas = await html2canvas(document.getElementById("openseadragon"));
    const dataUrl = canvas.toDataURL("image/jpeg",0.9);
    const body = { snapshot:dataUrl, viewState };
    const res = await fetch(`/save_view/${slide_uuid}`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify(body)
    });
    if(!res.ok) {
        alert("Save failed: " + (await res.text())); return;
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href=url; a.download="snapshot.jpg";
    document.body.appendChild(a); a.click(); a.remove();
    window.URL.revokeObjectURL(url);
    await fetchViews(); // refresh dropdown
}

async function loadLastView() {
    const res = await fetch(`/last_view/${slide_uuid}`);
    if(!res.ok) { alert("No view"); return; }
    const state = await res.json();
    if(state.status==="no view saved") {
        alert("No saved view"); return;
    }
    applyView(state);
}

async function fetchViews() {
    const res = await fetch(`/all_views/${slide_uuid}`);
    if (!res.ok) return;
    const views = await res.json();
    const select = document.getElementById("viewSelect");
    select.innerHTML = "";
    views.forEach(v => {
        const option = document.createElement("option");
        option.value = JSON.stringify(v);
        option.text = `${v.saved_at} (zoom ${v.zoom.toFixed(2)})`;
        select.appendChild(option);
    });
}

function loadSelectedView() {
    const select = document.getElementById("viewSelect");
    if (!select.value) { alert("No view selected"); return; }
    const state = JSON.parse(select.value);
    applyView(state);
}

function applyView(state) {
    viewer.viewport.zoomTo(state.zoom);
    viewer.viewport.panTo(new OpenSeadragon.Point(state.center_x, state.center_y));
    viewer.viewport.setRotation(state.rotation);
}

fetchViews();
