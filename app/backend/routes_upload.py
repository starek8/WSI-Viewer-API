from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import shutil

from db import Slide
from backend.dependencies import get_db
from backend.utils import extract_zip

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
SLIDES_DIR = BASE_DIR / "slides"
SLIDES_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_slide(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip containing .mrxs")

    slide_name = file.filename.rsplit(".", 1)[0]
    slide_dir = SLIDES_DIR / slide_name
    if slide_dir.exists():
        shutil.rmtree(slide_dir)
    slide_dir.mkdir(parents=True)

    zip_path = SLIDES_DIR / file.filename
    with open(zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extract_zip(zip_path, slide_dir)
    zip_path.unlink()

    mrxs_files = list(slide_dir.glob("*.mrxs"))
    if not mrxs_files:
        raise HTTPException(status_code=400, detail="No .mrxs file found in archive")

    slide = Slide(name=slide_name, path=str(slide_dir), filename=mrxs_files[0].name)
    db.add(slide)
    await db.commit()
    await db.refresh(slide)

    return RedirectResponse(url=f"/viewer/{slide.uuid}/{mrxs_files[0].name}", status_code=303)
