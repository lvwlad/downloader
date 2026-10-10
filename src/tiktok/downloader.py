import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import yt_dlp


class TikTokDownloader:
    def __init__(self, save_path: str = "tiktok_videos"):
        self.save_path = save_path
        self.create_save_directory()

    def create_save_directory(self) -> None:
        Path(self.save_path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_url(url: str) -> bool:
        try:
            parsed = urlsplit(url)
            return (
                parsed.scheme in {"http", "https"}
                and parsed.hostname in {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
                and not parsed.username
                and not parsed.password
                and parsed.port in {None, 80, 443}
                and parsed.path not in {"", "/"}
            )
        except ValueError:
            return False

    @staticmethod
    def progress_hook(data: Dict[str, Any]) -> None:
        if data["status"] == "finished":
            print("Download completed, finalizing...", flush=True)

    def get_filename(self, video_url: str, custom_name: Optional[str] = None) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = Path(custom_name).name if custom_name else "tiktok"
        return f"{name}_{timestamp}.mp4"

    @contextmanager
    def _youtube_dl(self, output_path: Optional[str] = None):
        options = {
            "format": "best",
            "noplaylist": True,
            "quiet": True,
            "progress_hooks": [self.progress_hook],
            "extractor_args": {"tiktok": {"webpage_download": True}},
        }
        if output_path:
            options["outtmpl"] = output_path
        proxy = os.environ.get("TIKTOK_PROXY", "").strip()
        if proxy:
            options["proxy"] = proxy

        # yt-dlp writes its cookie jar on exit. Copy the read-only mounted file
        # to a private temporary directory, so it can update the jar safely.
        with tempfile.TemporaryDirectory(prefix="toksave-cookies-") as directory:
            cookies = os.environ.get("TIKTOK_COOKIES_FILE", "").strip()
            if cookies:
                cookie_copy = Path(directory) / "cookies.txt"
                shutil.copyfile(cookies, cookie_copy)
                options["cookiefile"] = str(cookie_copy)
            with yt_dlp.YoutubeDL(options) as ydl:
                yield ydl

    def download_video(self, video_url: str, custom_name: Optional[str] = None) -> Optional[str]:
        if not self.validate_url(video_url):
            return None
        output_path = os.path.join(self.save_path, self.get_filename(video_url, custom_name))
        try:
            with self._youtube_dl(output_path) as ydl:
                ydl.download([video_url])
            return output_path if Path(output_path).is_file() else None
        except Exception:
            # Do not put proxy credentials or cookie contents in application logs.
            print("TikTok download failed. Check the URL and downloader configuration.", flush=True)
            return None

    def stream_video(self, video_url: str) -> subprocess.Popen:
        if not self.validate_url(video_url):
            raise ValueError("Invalid TikTok URL")
        with self._youtube_dl() as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info.get("url")
        if not direct_url:
            raise ValueError("TikTok did not provide a video URL")
        return subprocess.Popen(
            ["ffmpeg", "-i", direct_url, "-c", "copy", "-f", "mp4", "-movflags", "frag_keyframe+empty_moov", "pipe:1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )


DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parents[1] / "downloaded_tiktoks"
downloader = TikTokDownloader(save_path=os.environ.get("TIKTOK_DOWNLOAD_DIR") or str(DEFAULT_DOWNLOAD_DIR))
