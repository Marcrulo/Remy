# Remy: hands-free cooking assistant (WIP)

Phone camera streams to a local server; a small vision model + chat LLM answer questions about what the cook is doing.

## Layout
- `server/`  aiohttp stream server: phone sends JPEG frames over WebSocket, `/viewer` shows them, `/latest.jpg` serves the newest frame.
- `web/`     `capture.html` (phone page, rear camera, ~1 fps) and `viewer.html`.
- `agent/`   text REPL agent: chat LLM + `look(question)` tool backed by a small VLM. Stdlib only, talks to Ollama.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt
server/gen_cert.sh                       # self-signed cert for LAN IPs (camera needs HTTPS)
.venv/bin/python server/app.py           # phone: https://<pc-ip>:8443/  viewer: https://localhost:8443/viewer
python3 agent/agent.py --image path/to/frame.jpg   # or default: https://localhost:8443/latest.jpg
```
Models (Ollama): `ollama pull moondream` (vision) and a chat model, e.g. `qwen3:4b` / `qwen3:8b`.

## Findings so far
- **Phone could not reach the PC** when the PC was tethered to the phone's own hotspot (no request ever arrived; firewall was off). Untested fixes: `adb reverse tcp:8443 tcp:8443` over USB, or put both on a normal Wi-Fi router.
- **gemma3:4b** as the VLM: >400 s per image on a CPU-only laptop. Unusable.
- **moondream** (1.7 GB): ~3-4 s per image on CPU. Reliable for "Describe this image."; often returns an EMPTY answer for questions (emits stop token immediately). `look` therefore falls back to a caption.
- **Chat model for tool calling:** `qwen3:1.7b` (~2 s) never calls the tool; `qwen3:8b` calls it correctly but takes 11-44 s per reply on CPU. `qwen3:4b` was downloaded but NOT yet tested; that is the next step.
