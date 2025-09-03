from fastapi import FastAPI
from wsi import register_routes

def create_app() -> FastAPI:
    app = FastAPI(title="WSI Viewer API")
    register_routes(app)
    return app