from fastapi import FastAPI
from db import init_db
from wsi import register_routes

def create_app() -> FastAPI:
    app = FastAPI(title="WSI Viewer API")

    @app.on_event("startup")
    async def startup_event():
        await init_db()

    register_routes(app)
    return app