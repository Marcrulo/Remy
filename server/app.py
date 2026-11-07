"""Remy stream server: phone -> JPEG frames over WebSocket -> server -> viewers."""
import argparse
import asyncio
import json
import pathlib
import ssl
import time

from aiohttp import WSMsgType, web

ROOT = pathlib.Path(__file__).resolve().parent
WEB = ROOT.parent / "web"


class State:
    def __init__(self, save_dir, fps, quality, width):
        self.save_dir = save_dir
        self.settings = {"fps": fps, "quality": quality, "width": width}
        self.latest = None          # last JPEG bytes
        self.latest_ts = 0.0
        self.count = 0
        self.viewers = set()
        self.capturers = set()


async def index(request):
    return web.FileResponse(WEB / "capture.html")


async def viewer(request):
    return web.FileResponse(WEB / "viewer.html")


async def latest_jpg(request):
    st = request.app["st"]
    if not st.latest:
        raise web.HTTPNotFound(text="no frame yet")
    return web.Response(body=st.latest, content_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


async def ws_capture(request):
    st = request.app["st"]
    ws = web.WebSocketResponse(max_msg_size=8 * 1024 * 1024, heartbeat=15)
    await ws.prepare(request)
    st.capturers.add(ws)
    await ws.send_json({"type": "settings", **st.settings})
    print(f"[capture] connected from {request.remote}")
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                await handle_frame(st, msg.data)
                await ws.send_json({"type": "ack", "n": st.count})
    finally:
        st.capturers.discard(ws)
        print("[capture] disconnected")
    return ws


async def handle_frame(st, data):
    st.latest, st.latest_ts = data, time.time()
    st.count += 1
    if st.save_dir:
        (st.save_dir / f"{int(st.latest_ts * 1000)}.jpg").write_bytes(data)
    for v in list(st.viewers):
        try:
            await v.send_bytes(data)
        except ConnectionResetError:
            st.viewers.discard(v)


async def ws_view(request):
    st = request.app["st"]
    ws = web.WebSocketResponse(heartbeat=15)
    await ws.prepare(request)
    st.viewers.add(ws)
    if st.latest:
        await ws.send_bytes(st.latest)
    try:
        async for _ in ws:
            pass
    finally:
        st.viewers.discard(ws)
    return ws


async def status(request):
    st = request.app["st"]
    return web.json_response({
        "frames": st.count, "age_s": time.time() - st.latest_ts if st.latest else None,
        "capturers": len(st.capturers), "viewers": len(st.viewers), **st.settings})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8443)
    p.add_argument("--fps", type=float, default=1.0, help="capture rate requested from phone")
    p.add_argument("--quality", type=float, default=0.7, help="JPEG quality 0-1")
    p.add_argument("--width", type=int, default=768, help="max frame width in px")
    p.add_argument("--save", type=pathlib.Path, help="directory to store received frames")
    p.add_argument("--no-tls", action="store_true", help="plain HTTP (camera works only on localhost)")
    a = p.parse_args()

    if a.save:
        a.save.mkdir(parents=True, exist_ok=True)
    app = web.Application()
    app["st"] = State(a.save, a.fps, a.quality, a.width)
    app.add_routes([
        web.get("/", index), web.get("/viewer", viewer), web.get("/latest.jpg", latest_jpg),
        web.get("/status", status), web.get("/ws/capture", ws_capture), web.get("/ws/view", ws_view),
    ])

    ctx = None
    if not a.no_tls:
        cert, key = ROOT / "certs/cert.pem", ROOT / "certs/key.pem"
        if not cert.exists():
            raise SystemExit("No cert found. Run: server/gen_cert.sh")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
    scheme = "http" if a.no_tls else "https"
    print(f"Phone:  {scheme}://<this-pc-LAN-IP>:{a.port}/\nViewer: {scheme}://localhost:{a.port}/viewer")
    web.run_app(app, host=a.host, port=a.port, ssl_context=ctx, print=None)


if __name__ == "__main__":
    main()
