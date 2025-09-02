from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from openslide import OpenSlide, deepzoom
from pathlib import Path

SLIDES_DIR = Path(__file__).parent.parent / "slides"
SLIDES_DIR.mkdir(exist_ok=True)

# DeepZoom parameters
TILE_SIZE = 256
OVERLAP = 0
LIMIT_BOUNDS = True

def create_app() -> FastAPI:
    app = FastAPI(title="WSI Viewer API")

    @app.get("/", response_class=HTMLResponse)
    def root():
        return """
        <html>
        <head><title>WSI Viewer</title></head>
        <body>
            <h1>WSI Viewer</h1>
            <p>Open <a href="/viewer/example.svs">example.svs</a> if you placed it in /slides/</p>
        </body>
        </html>
        """

    @app.get("/slides")
    def list_slides():
        return {"slides": [f.name for f in SLIDES_DIR.glob("*") if f.is_file()]}

    @app.get("/viewer/{filename}", response_class=HTMLResponse)
    def viewer(filename: str):
        return f"""
        <html>
        <head>
            <script src="https://openseadragon.github.io/openseadragon/openseadragon.min.js"></script>
        </head>
        <body>
            <div id="openseadragon" style="width: 100%; height: 90vh;"></div>
            <script>
                OpenSeadragon({{
                    id: "openseadragon",
                    prefixUrl: "https://openseadragon.github.io/openseadragon/images/",
                    tileSources: "/dzi/{filename}"
                }});
            </script>
        </body>
        </html>
        """

    @app.get("/dzi/{filename}")
    def dzi_descriptor(filename: str):
        slide_path = SLIDES_DIR / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        slide = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        return FileResponse(dz.get_dzi("jpeg"))

    @app.get("/dzi/{filename}_files/{level}/{col}_{row}.jpeg")
    def dzi_tile(filename: str, level: int, col: int, row: int):
        slide_path = SLIDES_DIR / filename
        if not slide_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        slide = OpenSlide(str(slide_path))
        dz = deepzoom.DeepZoomGenerator(slide, TILE_SIZE, OVERLAP, LIMIT_BOUNDS)
        try:
            tile = dz.get_tile(level, (col, row))
        except Exception:
            raise HTTPException(status_code=404, detail="Tile not found")
        tile_path = f"/tmp/{filename}_{level}_{col}_{row}.jpeg"
        tile.save(tile_path, "JPEG")
        return FileResponse(tile_path)

    return app
