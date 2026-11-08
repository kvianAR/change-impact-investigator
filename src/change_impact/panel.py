"""Loopback-only Models panel with session-protected settings endpoints."""

from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit

from .ai import generate_text
from .credentials import CredentialError
from .models import ModelStore, SettingsConflict
from .providers import model_catalog


class ModelsPanel(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765, store=None):
        self.store = store if store is not None else ModelStore()
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), PanelHandler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "ChangeImpactModels"

    def log_message(self, *arguments):
        # Provider requests and credential bodies never enter access logs.
        pass

    def _send(self, status, content, content_type="application/json; charset=utf-8"):
        data = json.dumps(content).encode() if isinstance(content, (dict, list)) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, api=False):
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host", "").lower() not in hosts:
            self._send(403, {"error": "Unsupported host"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{host}" for host in hosts}:
            self._send(403, {"error": "Unsupported origin"})
            return False
        if api:
            supplied = self.headers.get("X-Impact-Token", "")
            if not supplied.isascii() or not secrets.compare_digest(supplied, self.server.token):
                self._send(403, {"error": "Panel session expired. Reload the Models panel."})
                return False
        return True

    def _body(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise ValueError("Send JSON data")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64_000 or self.headers.get("Transfer-Encoding"):
                raise ValueError()
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            raise ValueError("Invalid or oversized settings request") from None
        if not isinstance(body, dict):
            raise ValueError("Settings request must be a JSON object")
        return body

    @staticmethod
    def _revision(body):
        revision = body.get("revision")
        if type(revision) is not int or revision < 0:
            raise ValueError("A current settings revision is required")
        return revision

    def _dispatch(self, method):
        path = urlsplit(self.path).path
        api = path.startswith("/api/")
        if not self._authorized(api):
            return
        if method == "GET":
            if path == "/api/state":
                self._send(200, self.server.store.state())
                return
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
                "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/favicon.svg": ("favicon.svg", "image/svg+xml"),
            }
            if path in assets:
                name, content_type = assets[path]
                data = files("change_impact").joinpath("web", name).read_bytes()
                if name == "index.html":
                    data = data.replace(b"__PANEL_TOKEN__", self.server.token.encode())
                self._send(200, data, content_type)
                return
        elif method == "POST" and api:
            body = self._body()
            if path == "/api/catalog":
                provider = body.get("provider")
                connection = self.server.store.connection(
                    provider,
                    "catalog",
                    key_override=body.get("api_key"),
                    base_url=body.get("base_url"),
                    require_key=provider == "openai",
                )
                self._send(200, {"models": model_catalog(connection)})
                return
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[1] == "models" and parts[3] == "test":
                state = self.server.store.state()
                profile = next((item for item in state["models"] if item["id"] == parts[2]), None)
                if profile is None:
                    raise ValueError("Saved model not found")
                connection = self.server.store.connection(profile["provider"], profile["model"])
                generate_text(
                    connection, "Reply only with OK.", min(profile["max_output_tokens"], 1024)
                )
                self._send(
                    200, {"ok": True, "provider": profile["provider"], "model": profile["model"]}
                )
                return
            revision = self._revision(body)
            if path == "/api/models":
                state = self.server.store.save_model(body, revision)
            elif len(parts) == 3 and parts[1] == "providers":
                state = self.server.store.save_provider(parts[2], body, revision)
            elif len(parts) == 4 and parts[1] == "models" and parts[3] == "activate":
                state = self.server.store.activate(parts[2], revision)
            elif len(parts) == 4 and parts[1] == "models" and parts[3] == "delete":
                state = self.server.store.delete(parts[2], revision)
            else:
                self._send(404, {"error": "Endpoint not found"})
                return
            self._send(200, state)
            return
        self._send(404, {"error": "Page not found"})

    def _handle(self, method):
        try:
            self._dispatch(method)
        except SettingsConflict as error:
            self._send(409, {"error": str(error)})
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except CredentialError as error:
            self._send(503, {"error": str(error)})
        except RuntimeError as error:
            self._send(502, {"error": str(error)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            self._send(503, {"error": "Could not read or write local model settings"})
        except Exception:
            self._send(500, {"error": "The Models panel could not complete this request"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def serve_models(port=8765, open_browser=True):
    if not 0 <= port <= 65535:
        raise ValueError("Panel port must be between 0 and 65535")
    server = ModelsPanel(port)
    print(f"Models panel: {server.url}", flush=True)
    if open_browser:
        timer = threading.Timer(0.25, lambda: webbrowser.open(server.url))
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
