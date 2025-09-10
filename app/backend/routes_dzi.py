from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pathlib import Path
from openslide import OpenSlide, deepzoom
from io import BytesIO

from db import Slide
from backend.dependencies import get_db

router = APIRouter()

TILE_SIZE = 256
OVERLAP = 0
LIMIT_BOUNDS = True

@router.get("/dzi/{slide_uuid}/{filename}")
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

@router.get("/dzi/{slide_uuid}/{filename}_files/{level}/{col}_{row}.jpeg")
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
