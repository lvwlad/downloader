import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import app


class Response:
    def __init__(self, messages):
        start = next(message for message in messages if message["type"] == "http.response.start")
        self.status_code = start["status"]
        self.headers = {key.decode(): value.decode() for key, value in start["headers"]}
        self.content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


class ASGIClient:
    """Exercise the actual application without adding a test-only HTTP dependency."""
    def request(self, method, path, payload=None):
        async def run():
            messages = []
            headers = [(b"host", b"testserver")]
            body = b""
            if method == "POST":
                body = json.dumps(payload).encode()
                headers.append((b"content-type", b"application/json"))
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                     "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
                     "root_path": "", "headers": headers, "server": ("testserver", 80), "client": ("127.0.0.1", 1)}

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message):
                messages.append(message)

            await app(scope, receive, send)
            return Response(messages)
        return asyncio.run(run())

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, json):
        return self.request("POST", path, json)


class FrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.client = ASGIClient()

    def test_frontend_and_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="ru"', response.text)
        for asset in ("app.js", "styles.css", "favicon.svg"):
            self.assertEqual(self.client.get(f"/static/{asset}").status_code, 200)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    @patch("api.files.downloader.download_video")
    def test_rejects_invalid_links_without_downloading(self, download):
        for url in ("", "https://example.com/video/1", "https://www.tiktok.com.evil.com/video/1", "https://www.tiktok.com/", "https://user:pass@www.tiktok.com/video/1", "https://www.tiktok.com:9999/video/1"):
            with self.subTest(url=url):
                self.assertEqual(self.client.post("/api/tiktok", json=url).status_code, 400)
        download.assert_not_called()

    def test_preserves_string_body_contract(self):
        self.assertEqual(self.client.post("/api/tiktok", json={"url": "https://vm.tiktok.com/abc/"}).status_code, 422)

    @patch("api.files.downloader.download_video", return_value=None)
    def test_download_failure_is_readable(self, download):
        response = self.client.post("/api/tiktok", json="https://vm.tiktok.com/abc/")
        self.assertEqual(response.status_code, 502)
        self.assertIsInstance(response.json()["detail"], str)

    @patch("api.files.downloader.download_video", side_effect=RuntimeError("private detail"))
    def test_exception_does_not_leak_internal_details(self, download):
        response = self.client.post("/api/tiktok", json="https://vt.tiktok.com/abc/")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private detail", response.text)

    def test_valid_link_returns_mp4_with_length_and_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "test.mp4"
            video.write_bytes(b"fixture-mp4")
            with patch("api.files.downloader.download_video", return_value=str(video)) as download:
                response = self.client.post("/api/tiktok", json=" https://www.tiktok.com/@creator/video/123 ")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fixture-mp4")
            self.assertEqual(response.headers["content-type"], "video/mp4")
            self.assertEqual(response.headers["content-length"], "11")
            self.assertIn("attachment", response.headers["content-disposition"])
            self.assertEqual(download.call_args.args[0], "https://www.tiktok.com/@creator/video/123")
            self.assertTrue(download.call_args.kwargs["custom_name"].startswith("video_"))

    def test_missing_or_empty_file_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.mp4"
            empty.touch()
            for path in (empty, Path(directory) / "missing.mp4"):
                with patch("api.files.downloader.download_video", return_value=str(path)):
                    self.assertEqual(self.client.post("/api/tiktok", json="https://vm.tiktok.com/abc/").status_code, 502)


if __name__ == "__main__":
    unittest.main()
