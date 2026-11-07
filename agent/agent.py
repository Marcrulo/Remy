"""Remy agent (text REPL): a chat LLM that can call a `look` tool backed by a small vision model.

Everything runs through a local Ollama server. Stdlib only.
"""
import argparse
import base64
import json
import ssl
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434"

SYSTEM = (
    "You are Remy, a concise hands-free cooking assistant. Your replies are spoken aloud, "
    "so use one or two short sentences, no lists, no markdown.\n"
    "You have no eyes. You can only see through the `look` tool, which returns what the camera shows.\n"
    "RULE: if the user asks about anything currently visible or its state (is it done, what color, "
    "what is this, how does it look, my pan, my egg, my food) you MUST call `look` first and answer "
    "only from its result. Never guess or pretend to look. "
    "For general cooking knowledge (times, temperatures, substitutions), answer directly without the tool."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "look",
        "description": "Look at the cook's current camera view and answer a question about it.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "What to find out from the image"}},
            "required": ["question"],
        },
    },
}]


def post(path, body, timeout=600):
    req = urllib.request.Request(OLLAMA + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def load_image(src):
    """Return base64 JPEG from a file path or http(s) URL (self-signed certs allowed)."""
    if src.startswith(("http://", "https://")):
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        data = urllib.request.urlopen(src, timeout=10, context=ctx).read()
    else:
        data = open(src, "rb").read()
    return base64.b64encode(data).decode()


class Agent:
    def __init__(self, chat_model, vision_model, image_src, verbose=True):
        self.chat_model, self.vision_model, self.image_src = chat_model, vision_model, image_src
        self.verbose = verbose
        self.messages = [{"role": "system", "content": SYSTEM}]

    def log(self, *a):
        if self.verbose:
            print("   ·", *a, file=sys.stderr, flush=True)

    def look(self, question):
        try:
            img = load_image(self.image_src)
        except Exception as e:
            return f"Could not get an image: {e}"
        t = time.time()
        answer = self._vision(question, img)
        if not answer:
            # Small VLMs (moondream) sometimes emit nothing for questions but are reliable at
            # captioning. Fall back to a description the chat model can reason over.
            caption = self._vision("Describe this image.", img)
            answer = f"(Image description: {caption})" if caption else "The image could not be interpreted."
        self.log(f"vision ({self.vision_model}) {time.time() - t:.1f}s: {answer}")
        return answer

    def _vision(self, prompt, img):
        r = post("/api/chat", {"model": self.vision_model, "stream": False, "keep_alive": "30m",
                               "messages": [{"role": "user", "content": prompt, "images": [img]}]})
        return r["message"]["content"].strip()

    def run_tool(self, call):
        fn, args = call["function"]["name"], call["function"].get("arguments") or {}
        if fn == "look":
            return self.look(args.get("question", "Describe what you see."))
        return f"Unknown tool: {fn}"

    def ask(self, text, max_steps=4):
        self.messages.append({"role": "user", "content": text})
        for _ in range(max_steps):
            t = time.time()
            r = post("/api/chat", {"model": self.chat_model, "stream": False, "think": False,
                                   "messages": self.messages, "tools": TOOLS})
            msg = r["message"]
            self.messages.append(msg)
            self.log(f"chat ({self.chat_model}) {time.time() - t:.1f}s")
            calls = msg.get("tool_calls")
            if not calls:
                return (msg.get("content") or "").strip()
            for c in calls:
                self.log("tool call:", json.dumps(c["function"]))
                self.messages.append({"role": "tool", "tool_name": c["function"]["name"],
                                      "content": self.run_tool(c)})
        return "Sorry, I got stuck."


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chat-model", default="qwen3:1.7b")
    p.add_argument("--vision-model", default="moondream")
    p.add_argument("--image", default="https://localhost:8443/latest.jpg",
                   help="file path or URL of the current camera frame")
    p.add_argument("-q", "--question", help="ask one question and exit")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()
    agent = Agent(a.chat_model, a.vision_model, a.image, verbose=not a.quiet)
    if a.question:
        print(agent.ask(a.question))
        return
    print("Remy ready. Ctrl-D to quit.")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            break
        if text:
            print("remy>", agent.ask(text))


if __name__ == "__main__":
    main()
