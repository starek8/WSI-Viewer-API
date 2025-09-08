from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Body
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pathlib import Path
from openslide import OpenSlide, deepzoom
from PIL import Image
import shutil, zipfile, math
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
    async def root(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Slide))
        slides = result.scalars().all()

        slide_links = ""
        if slides:
            slide_links += "<h2>Dostępne slajdy:</h2><ul>"
            for s in slides:
                mrxs_files = list(Path(s.path).glob("*.mrxs"))
                if not mrxs_files:
                    continue
                slide_links += f'<li><a href="/viewer/{s.uuid}/{mrxs_files[0].name}">{s.name}</a></li>'
            slide_links += "</ul>"
        else:
            slide_links = "<p>Brak wgranych slajdów.</p>"

        return f"""
        <html>
        <head>
            <title>WSI Viewer</title>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #fafafa; text-align: center; padding: 2em; }}
                h1 {{ color: #2c3e50; }}
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
                .dropzone.dragover {{ background: #d6ebfa; }}
                ul {{ list-style: none; padding: 0; }}
                li {{ margin: 0.5em 0; }}
                a {{ color: #3498db; text-decoration: none; font-weight: bold; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <h1>Upload and View WSI (.zip with .mrxs + file_with_data)</h1>
            <form id="uploadForm">
                <div id="dropzone" class="dropzone">Drag & Drop .zip file here<br>or click to select</div>
                <input type="file" id="fileInput" name="file" accept=".zip" style="display:none" />
            </form>
            {slide_links}
            <script>
                const dropzone = document.getElementById("dropzone");
                const fileInput = document.getElementById("fileInput");

                dropzone.addEventListener("click", () => fileInput.click());
                dropzone.addEventListener("dragover", (e) => {{
                    e.preventDefault();
                    dropzone.classList.add("dragover");
                }});
                dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
                dropzone.addEventListener("drop", async (e) => {{
                    e.preventDefault();
                    dropzone.classList.remove("dragover");
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
            raise HTTPException(status_code=400, detail="Upload must be a .zip containing .mrxs + file_with_data")

        slide_name = file.filename.rsplit(".", 1)[0]
        slide_dir = SLIDES_DIR / slide_name
        if slide_dir.exists():
            shutil.rmtree(slide_dir)
        slide_dir.mkdir(parents=True)

        zip_path = SLIDES_DIR / file.filename
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Extract zip without keeping top-level folder
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
                #toolbar {{
                    position: absolute;
                    top: 1.5em;
                    left: 10vw;
                    z-index: 10;
                }}
                #toolbar button {{
                    padding: 0.6em 1.2em;
                    font-size: 1em;
                    border-radius: 8px;
                    border: none;
                    background: #3498db;
                    color: white;
                    cursor: pointer;
                    margin-right: 0.5em;
                }}
                #toolbar button:hover {{
                    background: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div id="toolbar">
                <button onclick="window.location.href='/'">Powrót na stronę główną</button>
                <button id="saveBtn">Zapisz widok</button>
            </div>
            <div id="openseadragon"></div>
            <script>
                const slide_uuid = "{slide_uuid}";
                const viewer = OpenSeadragon({{
                    id: "openseadragon",
                    prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
                    tileSources: "/dzi/{slide_uuid}/{filename}"
                }});

                document.getElementById("saveBtn").addEventListener("click", saveView);

                async function saveView() {{
                    const vp = viewer.viewport;

                    // Prostokąt widoczny na ekranie w jednostkach viewportu
                    const bounds = vp.getBounds(true); // bez rotacji; to co faktycznie widzisz
                    // Konwersja do pikseli obrazu (poziom 0)
                    const imgRect = vp.viewportToImageRectangle(bounds);

                    // Rozmiar okna (do ewentualnego przeskalowania JPG do rozdzielczości ekranu)
                    const container = viewer.container;
                    const target_w = container.clientWidth;
                    const target_h = container.clientHeight;

                    const body = {{
                        x: Math.round(imgRect.x),
                        y: Math.round(imgRect.y),
                        width: Math.round(imgRect.width),
                        height: Math.round(imgRect.height),
                        target_w,
                        target_h
                    }};

                    const res = await fetch(`/save_view/${{slide_uuid}}`, {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify(body)
                    }});

                    if (!res.ok) {{
                        const msg = await res.text();
                        alert("Failed to save view: " + msg);
                        return;
                    }}

                    // Auto-download
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "saved_view.jpg";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    window.URL.revokeObjectURL(url);
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
        """
        Odbiera współrzędne widocznego prostokąta w pikselach poziomu 0:
        { x, y, width, height, target_w, target_h }
        Zwraca JPG (attachment) – auto-download po stronie przeglądarki.
        """
        result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")

        # Walidacja wejścia
        for key in ("x", "y", "width", "height"):
            if key not in data:
                raise HTTPException(status_code=400, detail=f"Missing '{key}' in body")

        x = int(data["x"])
        y = int(data["y"])
        w = int(data["width"])
        h = int(data["height"])
        target_w = int(data.get("target_w") or 0)
        target_h = int(data.get("target_h") or 0)

        # Otwórz slajd
        mrxs_files = list(Path(slide.path).glob("*.mrxs"))
        if not mrxs_files:
            raise HTTPException(status_code=404, detail="No slide file found")
        slide_obj = OpenSlide(str(mrxs_files[0]))

        img_w, img_h = slide_obj.dimensions

        # Przytnij do granic obrazu i zabezpiecz przed ujemnymi/zerowymi rozmiarami
        x0 = max(0, min(x, img_w - 1))
        y0 = max(0, min(y, img_h - 1))
        x1 = max(x0 + 1, min(x + w, img_w))
        y1 = max(y0 + 1, min(y + h, img_h))

        crop_w = x1 - x0
        crop_h = y1 - y0

        # Zapisz stan (opcjonalnie – podgląd: środek i "zoom" wyliczone z prostokąta)
        center_x = (x0 + crop_w / 2) / img_w
        center_y = (y0 + crop_h / 2) / img_h
        approx_zoom = max(img_w / crop_w, img_h / crop_h)  # przybliżenie

        state = ViewState(
            slide_id=slide.id,
            zoom_level=float(approx_zoom),
            center_x=float(center_x),
            center_y=float(center_y)
        )
        db.add(state)
        await db.commit()
        await db.refresh(state)

        # Pobierz region z poziomu 0 i ewentualnie przeskaluj do rozdzielczości okna
        try:
            region = slide_obj.read_region((x0, y0), 0, (crop_w, crop_h)).convert("RGB")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"read_region failed: {e}")

        # Jeśli znamy rozmiar okna, skompresuj do niego (lżejszy plik, 1:1 z tym co widzi user)
        if target_w > 0 and target_h > 0:
            # Zachowaj aspekt prostokąta widoku – dopasuj do okna bez rozciągania
            scale = min(target_w / crop_w, target_h / crop_h)
            out_w = max(1, int(crop_w * scale))
            out_h = max(1, int(crop_h * scale))
            if out_w != crop_w or out_h != crop_h:
                region = region.resize((out_w, out_h), Image.LANCZOS)

        # Zapisz na dysku (opcjonalnie) i zwróć jako attachment
        snapshot_path = Path(slide.path) / f"view_{state.id}.jpg"
        region.save(snapshot_path, "JPEG", quality=90)

        # Nagłówek Content-Disposition wymusza pobranie przy bezpośrednim wejściu na URL,
        # ale my i tak robimy download przez blob – to dodatkowe zabezpieczenie.
        return FileResponse(
            snapshot_path,
            filename=f"view_{state.id}.jpg",
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
