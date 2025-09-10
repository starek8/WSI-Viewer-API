from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from db import init_db
from backend.routes_root import router as root_router
from backend.routes_upload import router as upload_router
from backend.routes_viewer import router as viewer_router
from backend.routes_dzi import router as dzi_router
from backend.routes_views import router as views_router

def create_app() -> FastAPI:
    app = FastAPI(title="WSI Viewer API")
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

    @app.on_event("startup")
    async def startup_event():
        await init_db()

    app.include_router(root_router)
    app.include_router(upload_router)
    app.include_router(viewer_router)
    app.include_router(dzi_router)
    app.include_router(views_router)

    return app
