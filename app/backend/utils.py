import shutil, zipfile
from pathlib import Path

def extract_zip(zip_path: Path, target_dir: Path):
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.namelist():
            parts = Path(member).parts
            target_path = target_dir / Path(*parts[1:]) if len(parts) > 1 else target_dir / Path(member)
            if member.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_path, "wb") as outfile, zip_ref.open(member) as src:
                    shutil.copyfileobj(src, outfile)
