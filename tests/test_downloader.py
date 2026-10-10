import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tiktok.downloader import TikTokDownloader


class DownloaderConfigurationTests(unittest.TestCase):
    def test_proxy_is_optional_and_read_at_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = TikTokDownloader(directory)
            for proxy in ("", "socks5://proxy.example.com:1080"):
                with self.subTest(proxy=proxy), patch.dict(os.environ, {"TIKTOK_PROXY": proxy, "TIKTOK_COOKIES_FILE": ""}), patch("tiktok.downloader.yt_dlp.YoutubeDL") as youtube_dl:
                    with downloader._youtube_dl():
                        options = youtube_dl.call_args.args[0]
                        self.assertEqual(options.get("proxy", ""), proxy)
                        self.assertNotIn("cookiesfrombrowser", options)
                        self.assertNotIn("cookiefile", options)

    def test_read_only_cookie_source_is_copied_and_temporary_copy_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source-cookies.txt"
            contents = "# Netscape HTTP Cookie File\n"
            source.write_text(contents)
            downloader = TikTokDownloader(directory)
            with patch.dict(os.environ, {"TIKTOK_PROXY": "", "TIKTOK_COOKIES_FILE": str(source)}), patch("tiktok.downloader.yt_dlp.YoutubeDL") as youtube_dl:
                with downloader._youtube_dl():
                    copy = Path(youtube_dl.call_args.args[0]["cookiefile"])
                    self.assertNotEqual(copy, source)
                    self.assertEqual(copy.read_text(), contents)
                    copy.write_text("updated cookie jar")
                self.assertFalse(copy.exists())
            self.assertEqual(source.read_text(), contents)

    def test_failed_download_does_not_return_a_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = TikTokDownloader(directory)
            with patch.dict(os.environ, {"TIKTOK_COOKIES_FILE": "", "TIKTOK_PROXY": ""}), patch("tiktok.downloader.yt_dlp.YoutubeDL") as youtube_dl:
                youtube_dl.return_value.__enter__.return_value.download.side_effect = RuntimeError("internal detail")
                self.assertIsNone(downloader.download_video("https://vm.tiktok.com/example/"))


if __name__ == "__main__":
    unittest.main()
