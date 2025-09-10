from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from db import Slide
from backend.dependencies import get_db
from fastapi import Request

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")

@router.get("/", response_class=HTMLResponse)
async def root(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Slide))
    slides = result.scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "slides": slides})
