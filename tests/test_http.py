import http.server
import threading
import time
import unittest

from cw import http as cw_http
from cw.errors import AdapterError


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            body = b'{"ok": true}'
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(body)
        elif self.path == "/503":
            self.send_response(503); self.end_headers()
        elif self.path == "/big":
            self.send_response(200); self.end_headers(); self.wfile.write(b"x" * 2048)
        elif self.path == "/slow":
            time.sleep(2); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
        elif self.path == "/ua":
            self.send_response(200); self.end_headers(); self.wfile.write(self.headers.get("User-Agent", "").encode())

    def log_message(self, *a):
        pass


class HttpFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def kind(self, path, **kw):
        with self.assertRaises(AdapterError) as cm:
            cw_http.fetch(self.base + path, **kw)
        return cm.exception.kind

    def test_ok_and_user_agent(self):
        self.assertEqual(cw_http.fetch(self.base + "/ok"), b'{"ok": true}')
        self.assertTrue(cw_http.fetch(self.base + "/ua").startswith(b"ConflictWatch/"))

    def test_http_error(self):
        self.assertEqual(self.kind("/503"), "http")

    def test_size_limit(self):
        self.assertEqual(self.kind("/big", max_bytes=1024), "size")

    def test_timeout(self):
        self.assertEqual(self.kind("/slow", timeout=0.5), "timeout")

    def test_network(self):
        with self.assertRaises(AdapterError) as cm:
            cw_http.fetch("http://127.0.0.1:9/", timeout=1)
        self.assertEqual(cm.exception.kind, "network")
