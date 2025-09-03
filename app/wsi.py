from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from openslide import OpenSlide, deepzoom
from pathlib import Path
import shutil, zipfile

BASE_DIR = Path(__file__).parent
SLIDES_DIR = BASE_DIR / "slides"   # extracted uploads live here
SLIDES_DIR.mkdir(exist_ok=True)

TILE_SIZE = 256
OVERLAP = 0
LIMIT_BOUNDS = True

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
            <h1>Upload and View WSI (.zip with .mrxs + .dat)</h1>
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
    async def upload_slide(file: UploadFile = File(...)):
        if not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Upload must be a .zip containing .mrxs + .dat files")

        slide_name = file.filename.rsplit(".", 1)[0]
        slide_dir = SLIDES_DIR / slide_name
        if slide_dir.exists():
            shutil.rmtree(slide_dir)
        slide_dir.mkdir(parents=True)

        zip_path = SLIDES_DIR / file.filename
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(slide_dir)
        zip_path.unlink()

        mrxs_files = list(slide_dir.glob("*.mrxs"))
        if not mrxs_files:
            raise HTTPException(status_code=400, detail="No .mrxs file found in archive")

        mrxs_file = mrxs_files[0]
        return RedirectResponse(url=f"/viewer/{slide_name}/{mrxs_file.name}", status_code=303)

    @app.get("/viewer/{slide}/{filename}", response_class=HTMLResponse)
    def viewer(slide: str, filename: str):
        return f"""
        <html>
        <head>
            <title>Viewer - {filename}</title>
            <script src="https://openseadragon.github.io/openseadragon/openseadragon.min.js"></script>
            <style>
                body, html {{ margin:0; padding:0; height:100%; }}
                #openseadragon {{ width: 100%; height: 100vh; background:#000; }}
            </style>
        </head>
        <body>
            <div id="openseadragon"></div>
            <script>
                OpenSeadragon({{
                    id: "openseadragon",
                    prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
                    tileSources: "/dzi/{slide}/{filename}"
                }});
            </script>
        </body>
        </html>
        """

    @app.get("/dzi/{slide}/{filename}")
    def dzi_descriptor(slide: str, filename: str):
        slide_path = SLIDES_DIR / slide / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        slide = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        return HTMLResponse(dz.get_dzi("jpeg"))

    @app.get("/dzi/{slide}/{filename}_files/{level}/{col}_{row}.jpeg")
    def dzi_tile(slide: str, filename: str, level: int, col: int, row: int):
        slide_path = SLIDES_DIR / slide / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        slide = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        try:
            tile = dz.get_tile(level, (col, row))
        except Exception:
            raise HTTPException(status_code=404, detail="Tile not found")
        tile_path = f"/tmp/{slide}_{level}_{col}_{row}.jpeg"
        tile.save(tile_path, "JPEG")
        return FileResponse(tile_path)
