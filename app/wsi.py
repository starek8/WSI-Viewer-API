from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pathlib import Path
from openslide import OpenSlide, deepzoom
import shutil, zipfile
from io import BytesIO

from db import Slide, ViewState, AsyncSessionLocal

BASE_DIR = Path(__file__).parent
SLIDES_DIR = BASE_DIR / "slides"   # extracted uploads live here
SLIDES_DIR.mkdir(exist_ok=True)

TILE_SIZE = 256
OVERLAP = 0
LIMIT_BOUNDS = True


# Dependency to get DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


def register_routes(app: FastAPI):
    @app.get("/", response_class=HTMLResponse)
    def root():
        return """
        <html>
        <head>
            <title>WSI Viewer</title>
            <style>
                body { font-family: Arial, sans-serif; background-color: #fafafa; text-align: center; padding: 40px; }
                h1 { color: #2c3e50; }
                .dropzone {
                    border: 3px dashed #3498db;
                    border-radius: 10px;
                    padding: 50px;
                    background: #ecf6fb;
                    color: #555;
                    cursor: pointer;
                    transition: background 0.3s;
                    margin: 30px auto;
                    width: 60%;
                }
                .dropzone.dragover { background: #d6ebfa; }
            </style>
        </head>
        <body>
            <h1>Upload and View WSI (.zip with .mrxs + file_with_data)</h1>
            <form id="uploadForm">
                <div id="dropzone" class="dropzone">Drag & Drop .zip file here<br>or click to select</div>
                <input type="file" id="fileInput" name="file" accept=".zip" style="display:none" />
            </form>
            <script>
                const dropzone = document.getElementById("dropzone");
                const fileInput = document.getElementById("fileInput");

                dropzone.addEventListener("click", () => fileInput.click());
                dropzone.addEventListener("dragover", (e) => {
                    e.preventDefault();
                    dropzone.classList.add("dragover");
                });
                dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
                dropzone.addEventListener("drop", async (e) => {
                    e.preventDefault();
                    dropzone.classList.remove("dragover");
                    const file = e.dataTransfer.files[0];
                    if (file) await uploadFile(file);
                });
                fileInput.addEventListener("change", async () => {
                    if (fileInput.files.length > 0) await uploadFile(fileInput.files[0]);
                });

                async function uploadFile(file) {
                    const formData = new FormData();
                    formData.append("file", file);
                    const res = await fetch("/upload", { method: "POST", body: formData });
                    if (res.redirected) {
                        window.location.href = res.url;
                    } else {
                        alert("Upload failed!");
                    }
                }
            </script>
        </body>
        </html>
        """

    @app.post("/upload")
    async def upload_slide(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
        if not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Upload must be a .zip containing .mrxs + file_with_data")

        slide_name = file.filename.rsplit(".", 1)[0]
        slide_dir = SLIDES_DIR / slide_name
        if slide_dir.exists():
            shutil.rmtree(slide_dir)
        slide_dir.mkdir(parents=True)

        zip_path = SLIDES_DIR / file.filename
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Extract zip without keeping top-level folder (normalize structure)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                parts = Path(member).parts
                if len(parts) > 1:
                    target_path = slide_dir / Path(*parts[1:])
                else:
                    target_path = slide_dir / Path(member)

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

        mrxs_file = mrxs_files[0]

        # Save slide metadata to DB
        slide = Slide(name=slide_name, path=str(slide_dir))
        db.add(slide)
        await db.commit()
        await db.refresh(slide)

        return RedirectResponse(url=f"/viewer/{slide.uuid}/{mrxs_file.name}", status_code=303)

    @app.get("/viewer/{slide_uuid}/{filename}", response_class=HTMLResponse)
    async def viewer(slide_uuid: str, filename: str, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        return f"""
        <html>
        <head>
            <title>Viewer - {filename}</title>
            <script src="https://openseadragon.github.io/openseadragon/openseadragon.min.js"></script>
            <style>
                body, html {{ margin:0; padding:0; height:100%; }}
                #openseadragon {{ width: 100%; height: 100vh; background:#000; }}
                #toolbar {{ position: absolute; top: 10px; left: 10px; z-index: 10; }}
            </style>
        </head>
        <body>
            <div id="toolbar">
                <button onclick="saveView()">Save View</button>
            </div>
            <div id="openseadragon"></div>
            <script>
                const slide_uuid = "{slide_uuid}";
                const viewer = OpenSeadragon({{
                    id: "openseadragon",
                    prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
                    tileSources: "/dzi/{slide_uuid}/{filename}"
                }});

                async function saveView() {{
                    const vp = viewer.viewport;
                    const data = {{
                        zoom: vp.getZoom(),
                        center_x: vp.getCenter().x,
                        center_y: vp.getCenter().y
                    }};
                    await fetch(`/save_view/${{slide_uuid}}`, {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify(data)
                    }});
                    alert("View saved!");
                }}
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
        slide_obj = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide_obj, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
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

        slide_obj = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide_obj, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        try:
            tile = dz.get_tile(level, (col, row))
        except Exception:
            raise HTTPException(status_code=404, detail="Tile not found")

        buf = BytesIO()
        tile.save(buf, format="JPEG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")

    @app.post("/save_view/{slide_uuid}")
    async def save_view(slide_uuid: str, data: dict = Body(...), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        state = ViewState(
            slide_id=slide.id,
            zoom_level=data["zoom"],
            center_x=data["center_x"],
            center_y=data["center_y"]
        )
        db.add(state)
        await db.commit()
        return {"status": "saved"}

    @app.get("/last_view/{slide_uuid}")
    async def last_view(slide_uuid: str, db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        result = await db.execute(
            select(ViewState).where(ViewState.slide_id == slide.id).order_by(ViewState.saved_at.desc())
        )
        state = result.scalars().first()
        if not state:
            return {"status": "no view saved"}

        return {
            "zoom": state.zoom_level,
            "center_x": state.center_x,
            "center_y": state.center_y,
            "saved_at": state.saved_at
        }
