from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.templating import Jinja2Templates
from fastapi import Request

from db import Slide
from backend.dependencies import get_db

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")

@router.get("/viewer/{slide_uuid}/{filename}", response_class=HTMLResponse)
async def viewer(request: Request, slide_uuid: str, filename: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Slide).where(Slide.uuid == slide_uuid))
    slide = result.scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    return templates.TemplateResponse(
        "viewer.html",
        {"request": request, "slide_uuid": slide_uuid, "filename": filename}
    )