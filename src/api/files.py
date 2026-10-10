from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from tiktok.downloader import downloader

router = APIRouter(prefix="/api")
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}


@router.post("/tiktok")
def download_file(url: str = Body(...)):
    url = url.strip()
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in TIKTOK_HOSTS
            and not parsed.username
            and not parsed.password
            and parsed.port in {None, 80, 443}
            and parsed.path not in {"", "/"}
        )
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, "Вставьте ссылку на видео с tiktok.com, vm.tiktok.com или vt.tiktok.com.")

    # The downloader is synchronous. FastAPI runs this handler in its thread pool.
    # Unique names prevent concurrent requests from overwriting each other's file.
    try:
        filename = downloader.download_video(url, custom_name=f"video_{uuid4().hex[:12]}")
        path = Path(filename) if filename else None
        if path is None or not path.is_file() or path.stat().st_size == 0:
            raise HTTPException(502, "Не удалось получить видео. Проверьте ссылку и настройки загрузчика, затем попробуйте ещё раз.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Загрузчик недоступен. Проверьте подключение и настройки загрузчика.") from None

    return FileResponse(path, media_type="video/mp4", filename=path.name)
