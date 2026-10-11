from __future__ import annotations

import html
import ipaddress
import json
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .store import ScreenshotRecord, ScreenshotStore

PAGE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#10131a"><title>LanShot 手机接收器</title>
<style>
:root{color-scheme:dark;--bg:#0b0d12;--card:#151923;--text:#f5f7fb;--muted:#98a2b3;--accent:#6c7cff;--line:#292f3d}*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at 50% -10%,#252b55 0,transparent 40%),var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
main{width:min(920px,100%);margin:auto;padding:24px 16px 48px}.head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.brand{font-size:22px;font-weight:750}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#42d392;box-shadow:0 0 12px #42d392;margin-right:7px}.status{color:var(--muted);font-size:13px}
.card{background:color-mix(in srgb,var(--card) 92%,transparent);border:1px solid var(--line);border-radius:20px;overflow:hidden;box-shadow:0 20px 70px #0008}.empty{padding:20vh 24px;text-align:center;color:var(--muted)}.empty b{display:block;color:var(--text);font-size:20px;margin-bottom:8px}
#shot{display:none;width:100%;height:auto;max-height:72vh;object-fit:contain;background:#050608}.meta{display:none;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-top:1px solid var(--line)}.info{min-width:0;color:var(--muted);font-size:13px}.actions{display:flex;gap:8px}.button{border:0;border-radius:11px;padding:10px 15px;background:var(--accent);color:white;font:inherit;font-weight:650;text-decoration:none;cursor:pointer}.button.secondary{background:#272d3b}footer{text-align:center;color:#667085;font-size:12px;margin-top:16px}
@media(max-width:560px){main{padding:14px 10px 32px}.head{padding:0 4px}.meta{align-items:flex-start;flex-direction:column}.actions{width:100%}.button{flex:1;text-align:center}}
</style></head><body><main><div class="head"><div class="brand">LanShot</div><div class="status"><i class="dot"></i><span id="state">正在连接电脑</span></div></div>
<div class="card"><div class="empty" id="empty"><b>等待电脑截图</b>在电脑按 Ctrl + Alt + A，整个桌面截图会自动出现在这里。</div><img id="shot" alt="电脑截图"><div class="meta" id="meta"><div class="info" id="info"></div><div class="actions"><button class="button secondary" id="share">分享</button><a class="button" id="download" download>保存图片</a></div></div></div><footer>手机和电脑需保持在同一个局域网内 · 页面保持打开即可自动接收</footer></main>
<script>
const token=new URLSearchParams(location.search).get('token')||'';let latest=0;const $=id=>document.getElementById(id);
async function poll(){try{const r=await fetch('/api/status?token='+encodeURIComponent(token)+'&after='+latest,{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();$('state').textContent='已连接电脑';if(d.latest&&d.latest.id!==latest){latest=d.latest.id;const u=d.latest.url+'?token='+encodeURIComponent(token)+'&v='+latest;$('shot').src=u;$('shot').style.display='block';$('empty').style.display='none';$('meta').style.display='flex';$('info').textContent=d.latest.width+' × '+d.latest.height+' · '+new Date(d.latest.created_at*1000).toLocaleTimeString();$('download').href=u;document.title='收到新截图 · LanShot'}}catch(e){$('state').textContent='连接中断，正在重试'}finally{setTimeout(poll,900)}}
$('share').onclick=async()=>{try{const r=await fetch($('download').href);const b=await r.blob();const f=new File([b],'LanShot.png',{type:'image/png'});if(navigator.canShare&&navigator.canShare({files:[f]}))await navigator.share({files:[f],title:'LanShot 截图'});else throw Error()}catch(e){$('download').click()}};poll();
</script></body></html>'''


def _private_ip_score(value: str) -> tuple[int, int]:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return (99, 0)
    if ip.version != 4 or ip.is_loopback or ip.is_link_local or not ip.is_private:
        return (99, 0)
    if value.startswith("192.168."):
        return (0, 0)
    if value.startswith("10."):
        return (1, 0)
    return (2, 0)


def local_ipv4() -> str:
    # A UDP connect selects the default LAN route without sending application data.
    # Prefer it over hostname results, which often include VPN and virtual adapters.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            routed = sock.getsockname()[0]
            if _private_ip_score(routed)[0] < 99:
                return routed
    except OSError:
        pass
    candidates: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(item[4][0])
    except OSError:
        pass
    valid = sorted(candidates, key=lambda value: (_private_ip_score(value), value))
    return valid[0] if valid and _private_ip_score(valid[0])[0] < 99 else "127.0.0.1"


class LanShotHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], store: ScreenshotStore, token: str):
        self.store = store
        self.access_token = token
        super().__init__(address, LanShotHandler)


class LanShotHandler(BaseHTTPRequestHandler):
    server: LanShotHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [""])[0]
        if token != self.server.access_token:
            self._send_text(HTTPStatus.FORBIDDEN, "配对地址无效，请从电脑托盘重新打开配对页面。")
            return
        if parsed.path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif parsed.path == "/api/status":
            self._send_status()
        elif parsed.path.startswith("/image/") and parsed.path.endswith(".png"):
            self._send_image(parsed.path)
        else:
            self._send_text(HTTPStatus.NOT_FOUND, "未找到")

    def _send_status(self) -> None:
        record = self.server.store.latest()
        payload: dict[str, object] = {"ok": True, "latest": None}
        if record:
            payload["latest"] = {
                "id": record.image_id,
                "width": record.width,
                "height": record.height,
                "created_at": record.created_at,
                "url": f"/image/{record.image_id}.png",
            }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(HTTPStatus.OK, "application/json; charset=utf-8", data)

    def _send_image(self, path: str) -> None:
        try:
            image_id = int(Path(path).stem)
        except ValueError:
            self._send_text(HTTPStatus.BAD_REQUEST, "图片编号无效")
            return
        record = self.server.store.get(image_id)
        if not record or not record.path.is_file():
            self._send_text(HTTPStatus.NOT_FOUND, "截图已过期")
            return
        try:
            data = record.path.read_bytes()
        except OSError:
            self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "读取截图失败")
            return
        self._send(HTTPStatus.OK, "image/png", data, cache="private, max-age=86400")

    def _send_text(self, status: HTTPStatus, text: str) -> None:
        safe = f"<!doctype html><meta charset=utf-8><title>LanShot</title><p>{html.escape(text)}</p>"
        self._send(status, "text/html; charset=utf-8", safe.encode("utf-8"))

    def _send(self, status: HTTPStatus, content_type: str, data: bytes, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


class MobileServer:
    def __init__(self, store: ScreenshotStore, token: str, preferred_port: int = 8765) -> None:
        self.store = store
        self.token = token
        self.preferred_port = preferred_port
        self.httpd: LanShotHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if not self.httpd:
            raise RuntimeError("server is not running")
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{local_ipv4()}:{self.port}/?token={quote(self.token)}"

    def start(self) -> None:
        last_error: OSError | None = None
        candidates = [self.preferred_port, *range(8765, 8786), 0]
        for port in dict.fromkeys(candidates):
            try:
                self.httpd = LanShotHTTPServer(("0.0.0.0", port), self.store, self.token)
                break
            except OSError as exc:
                last_error = exc
        if not self.httpd:
            raise OSError("无法启动手机接收服务") from last_error
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="LanShotWeb", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


