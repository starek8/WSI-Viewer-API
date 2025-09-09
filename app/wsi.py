# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pathlib import Path
from openslide import OpenSlide, deepzoom
from io import BytesIO
from base64 import b64decode
import shutil, zipfile

from db import Slide, ViewState, AsyncSessionLocal

BASE_DIR = Path(__file__).parent
SLIDES_DIR = BASE_DIR / "slides"
SLIDES_DIR.mkdir(exist_ok=True)

TILE_SIZE = 256
OVERLAP = 0
LIMIT_BOUNDS = True


# Dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def register_routes(app: FastAPI):
    @app.get("/", response_class=HTMLResponse)
    async def root(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide))
        slides = result.scalars().all()

        slide_links = ""
        if slides:
            slide_links += "<h2>Available Slides:</h2><ul>"
            for s in slides:
                mrxs_files = list(Path(s.path).glob("*.mrxs"))
                if not mrxs_files:
                    continue
                slide_links += f'<li><a href="/viewer/{s.uuid}/{mrxs_files[0].name}">{s.name}</a></li>'
            slide_links += "</ul>"
        else:
            slide_links = "<p>No slides uploaded.</p>"

        return f"""
        <html>
        <head>
            <title>WSI Viewer</title>
            <style>
                body {{ font-family: Arial, sans-serif; background:#fafafa; text-align:center; padding:2em; }}
                h1 {{ color:#2c3e50; }}
                .dropzone {{
                    border: 3px dashed #3498db;
                    border-radius: 10px;
                    padding: 3em;
                    background: #ecf6fb;
                    color: #555;
                    cursor: pointer;
                    transition: background 0.3s;
                    margin: 2em auto;
                    width: 60%;
                }}
                .dropzone.dragover {{ background:#d6ebfa; }}
                ul {{ list-style:none; padding:0; }}
                li {{ margin:0.5em 0; }}
                a {{ color:#3498db; text-decoration:none; font-weight:bold; }}
                a:hover {{ text-decoration:underline; }}
            </style>
        </head>
        <body>
            <h1>Upload and View WSI (.zip with .mrxs + data)</h1>
            <form id="uploadForm">
                <div id="dropzone" class="dropzone">Drag & Drop .zip file here<br>or click to select</div>
                <input type="file" id="fileInput" name="file" accept=".zip" style="display:none" />
            </form>
            {slide_links}
            <script>
                const dropzone = document.getElementById("dropzone");
                const fileInput = document.getElementById("fileInput");

                dropzone.addEventListener("click", () => fileInput.click());
                dropzone.addEventListener("dragover", e => {{
                    e.preventDefault(); dropzone.classList.add("dragover");
                }});
                dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
                dropzone.addEventListener("drop", async e => {{
                    e.preventDefault(); dropzone.classList.remove("dragover");
                    const file = e.dataTransfer.files[0];
                    if (file) await uploadFile(file);
                }});
                fileInput.addEventListener("change", async () => {{
                    if (fileInput.files.length > 0) await uploadFile(fileInput.files[0]);
                }});

                async function uploadFile(file) {{
                    const formData = new FormData();
                    formData.append("file", file);
                    const res = await fetch("/upload", {{ method: "POST", body: formData }});
                    if (res.redirected) {{
                        window.location.href = res.url;
                    }} else {{
                        alert("Upload failed!");
                    }}
                }}
            </script>
        </body>
        </html>
        """

    @app.post("/upload")
    async def upload_slide(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        if not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Upload must be a .zip containing .mrxs")

        slide_name = file.filename.rsplit(".", 1)[0]
        slide_dir = SLIDES_DIR / slide_name
        if slide_dir.exists():
            shutil.rmtree(slide_dir)
        slide_dir.mkdir(parents=True)

        zip_path = SLIDES_DIR / file.filename
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                parts = Path(member).parts
                target_path = slide_dir / Path(*parts[1:]) if len(parts) > 1 else slide_dir / Path(member)
                if member.endswith("/"):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, "wb") as outfile, zip_ref.open(member) as src:
                        shutil.copyfileobj(src, outfile)
        zip_path.unlink()

        mrxs_files = list(slide_dir.glob("*.mrxs"))
        if not mrxs_files:
            raise HTTPException(status_code=400, detail="No .mrxs file found in archive")

        slide = Slide(name=slide_name, path=str(slide_dir))
        db.add(slide)
        await db.commit()
        await db.refresh(slide)

        return RedirectResponse(url=f"/viewer/{slide.uuid}/{mrxs_files[0].name}", status_code=303)

    @app.get("/viewer/{slide_uuid}/{filename}", response_class=HTMLResponse)
    async def viewer(slide_uuid: str, filename: str, db: AsyncSession = Depends(get_db)):
        return f"""
        <html>
        <head>
            <title>Viewer - {filename}</title>
            <script src="https://openseadragon.github.io/openseadragon/openseadragon.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
            <style>
                body, html {{ margin:0; padding:0; height:100%; }}
                #openseadragon {{ width:100%; height:100vh; background:#000; }}
                #toolbar {{
                    position:absolute; top:1em; left:10vw; z-index:10;
                }}
                #toolbar button {{
                    padding:0.6em 1.2em; font-size:1em; border-radius:8px;
                    border:none; background:#3498db; color:white; cursor:pointer;
                    margin-right:0.5em;
                }}
                #toolbar button:hover {{ background:#2980b9; }}
            </style>
        </head>
        <body>
            <div id="toolbar">
                <button onclick="window.location.href='/'">Back</button>
                <button id="saveBtn">Save View</button>
                <button id="loadBtn">Load Last View</button>
                <select id="viewSelect"></select>
                <button id="loadSelectedBtn">Load Selected View</button>
            </div>
            <div id="openseadragon"></div>
            <script>
                const slide_uuid = "{slide_uuid}";
                const viewer = OpenSeadragon({{
                    id:"openseadragon",
                    prefixUrl:"https://openseadragon.github.io/openseadragon/images/",
                    tileSources:"/dzi/{slide_uuid}/{filename}"
                }});

                document.getElementById("saveBtn").addEventListener("click", saveView);
                document.getElementById("loadBtn").addEventListener("click", loadLastView);
                document.getElementById("loadSelectedBtn").addEventListener("click", loadSelectedView);

                async function saveView() {{
                    const vp = viewer.viewport;
                    const viewState = {{
                        zoom: vp.getZoom(),
                        center_x: vp.getCenter().x,
                        center_y: vp.getCenter().y,
                        rotation: vp.getRotation()
                    }};
                    const canvas = await html2canvas(document.getElementById("openseadragon"));
                    const dataUrl = canvas.toDataURL("image/jpeg",0.9);
                    const body = {{ snapshot:dataUrl, viewState }};
                    const res = await fetch(`/save_view/${{slide_uuid}}`, {{
                        method:"POST", headers:{{"Content-Type":"application/json"}},
                        body:JSON.stringify(body)
                    }});
                    if(!res.ok) {{
                        alert("Save failed: " + (await res.text())); return;
                    }}
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href=url; a.download="snapshot.jpg";
                    document.body.appendChild(a); a.click(); a.remove();
                    window.URL.revokeObjectURL(url);
                    await fetchViews(); // refresh dropdown
                }}

                async function loadLastView() {{
                    const res = await fetch(`/last_view/${{slide_uuid}}`);
                    if(!res.ok) {{ alert("No view"); return; }}
                    const state = await res.json();
                    if(state.status==="no view saved") {{
                        alert("No saved view"); return;
                    }}
                    applyView(state);
                }}

                async function fetchViews() {{
                    const res = await fetch(`/all_views/${{slide_uuid}}`);
                    if (!res.ok) return;
                    const views = await res.json();
                    const select = document.getElementById("viewSelect");
                    select.innerHTML = "";
                    views.forEach(v => {{
                        const option = document.createElement("option");
                        option.value = JSON.stringify(v);
                        option.text = `${{v.saved_at}} (zoom ${{v.zoom.toFixed(2)}})`;
                        select.appendChild(option);
                    }});
                }}

                function loadSelectedView() {{
                    const select = document.getElementById("viewSelect");
                    if (!select.value) {{ alert("No view selected"); return; }}
                    const state = JSON.parse(select.value);
                    applyView(state);
                }}

                function applyView(state) {{
                    viewer.viewport.zoomTo(state.zoom);
                    viewer.viewport.panTo(new OpenSeadragon.Point(state.center_x, state.center_y));
                    viewer.viewport.setRotation(state.rotation);
                }}

                fetchViews(); // load list on start
            </script>
        </body>
        </html>
        """

    @app.get("/dzi/{slide_uuid}/{filename}")
    async def dzi_descriptor(slide_uuid: str, filename: str, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        slide_path = Path(slide.path) / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        dz = deepzoom.DeepZoomGenerator(OpenSlide(str(slide_path)), TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        return Response(dz.get_dzi("jpeg"), media_type="application/xml")

    @app.get("/dzi/{slide_uuid}/{filename}_files/{level}/{col}_{row}.jpeg")
    async def dzi_tile(slide_uuid: str, filename: str, level: int, col: int, row: int, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        slide_path = Path(slide.path) / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        dz = deepzoom.DeepZoomGenerator(OpenSlide(str(slide_path)), TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        try:
            tile = dz.get_tile(level, (col, row))
        except Exception:
            raise HTTPException(status_code=404, detail="Tile not found")

        buf = BytesIO()
        tile.save(buf, format="JPEG"); buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")

    @app.post("/save_view/{slide_uuid}")
    async def save_view(slide_uuid: str, data: dict = Body(...), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        snapshot_b64 = data.get("snapshot")
        view = data.get("viewState")
        if not snapshot_b64 or not view:
            raise HTTPException(status_code=400, detail="Missing snapshot or viewState")

        header, encoded = snapshot_b64.split(",", 1)
        img_bytes = b64decode(encoded)

        state = ViewState(
            slide_id=slide.id,
            zoom_level=float(view.get("zoom",1.0)),
            center_x=float(view.get("center_x",0.5)),
            center_y=float(view.get("center_y",0.5)),
            rotation=float(view.get("rotation",0.0))
        )
        db.add(state); await db.commit(); await db.refresh(state)

        return StreamingResponse(
            BytesIO(img_bytes),
            media_type="image/jpeg",
            headers={"Content-Disposition": f'attachment; filename="view_{state.id}.jpg"'}
        )

    @app.get("/last_view/{slide_uuid}")
    async def last_view(slide_uuid: str, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        result = await db.execute(
            select(ViewState).where(ViewState.slide_id==slide.id).order_by(ViewState.saved_at.desc())
        )
        state = result.scalars().first()
        if not state:
            return {"status":"no view saved"}

        return {
            "zoom": state.zoom_level,
            "center_x": state.center_x,
            "center_y": state.center_y,
            "rotation": state.rotation,
            "saved_at": state.saved_at
        }

    @app.get("/all_views/{slide_uuid}")
    async def all_views(slide_uuid: str, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        result = await db.execute(
            select(ViewState).where(ViewState.slide_id == slide.id).order_by(ViewState.saved_at.desc())
        )
        states = result.scalars().all()
        return [
            {
                "id": s.id,
                "zoom": s.zoom_level,
                "center_x": s.center_x,
                "center_y": s.center_y,
                "rotation": s.rotation,
                "saved_at": s.saved_at.isoformat(),
            }
            for s in states
        ]
