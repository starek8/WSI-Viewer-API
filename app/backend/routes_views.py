from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from base64 import b64decode
from io import BytesIO

from db import Slide, ViewState
from backend.dependencies import get_db

router = APIRouter()

@router.post("/save_view/{slide_uuid}")
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

@router.get("/last_view/{slide_uuid}")
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

@router.get("/all_views/{slide_uuid}")
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
