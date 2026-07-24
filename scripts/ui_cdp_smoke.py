"""Browser-level smoke test using Chrome DevTools Protocol.

This fallback is used when the workspace Playwright runtime is unavailable.
It drives real mouse/keyboard input, captures console exceptions and saves
desktop/mobile screenshots for visual review.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests
import websocket


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "ui"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
TARGET = "http://127.0.0.1:8765/"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class CDP:
    def __init__(self, url: str):
        self.ws = websocket.create_connection(url, timeout=10, origin="http://127.0.0.1")
        self.next_id = 0
        self.exceptions: list[str] = []

    def close(self):
        self.ws.close()

    def call(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        call_id = self.next_id
        self.ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("method") == "Runtime.exceptionThrown":
                details = message.get("params", {}).get("exceptionDetails", {})
                self.exceptions.append(details.get("text", "JavaScript exception"))
            if message.get("id") == call_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method}: {message['error']}")
                return message.get("result", {})

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        })
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            description = details.get("exception", {}).get("description", "")
            raise AssertionError(f"{details.get('text', 'evaluation failed')}: {description}")
        return result.get("result", {}).get("value")

    def wait(self, expression: str, timeout: float = 12.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.15)
        raise AssertionError(f"Timed out waiting for: {expression}")

    def click(self, selector: str):
        quoted = json.dumps(selector)
        point = self.evaluate(
            f"(() => {{ const e=document.querySelector({quoted}); if(!e) return null; "
            "const r=e.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2}; })()"
        )
        if not point:
            raise AssertionError(f"Missing click target: {selector}")
        for event_type, buttons in (("mousePressed", 1), ("mouseReleased", 0)):
            self.call("Input.dispatchMouseEvent", {
                "type": event_type, "x": point["x"], "y": point["y"],
                "button": "left", "buttons": buttons, "clickCount": 1,
            })

    def insert_text(self, selector: str, text: str):
        self.click(selector)
        self.call("Input.insertText", {"text": text})

    def key(self, key: str, code: str):
        for event_type in ("keyDown", "keyUp"):
            self.call("Input.dispatchKeyEvent", {"type": event_type, "key": key, "code": code})

    def screenshot(self, filename: str):
        data = self.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})["data"]
        (ARTIFACTS / filename).write_bytes(base64.b64decode(data))

    def navigate(self, url: str):
        self.call("Page.navigate", {"url": url})
        self.wait("document.readyState === 'complete'")


def main() -> None:
    if not CHROME.exists():
        raise SystemExit("Chrome executable not found")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    profile = ARTIFACTS / f"chrome-profile-{port}"
    profile.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["NO_PROXY"] = "127.0.0.1,localhost"
    process = subprocess.Popen([
        str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-allow-origins=*",
        f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        version_url = f"http://127.0.0.1:{port}/json/version"
        for _ in range(80):
            try:
                requests.get(version_url, timeout=.3).raise_for_status()
                break
            except requests.RequestException:
                time.sleep(.1)
        else:
            raise AssertionError("Chrome debugging endpoint did not start")

        target_url = f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(TARGET, safe=':/?=&')}"
        target = requests.put(target_url, timeout=3).json()
        cdp = CDP(target["webSocketDebuggerUrl"])
        try:
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call("Network.enable")
            cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            cdp.navigate(TARGET)
            cdp.wait("document.querySelectorAll('.object-card').length === 3")
            assert cdp.evaluate("document.querySelectorAll('.capability-card').length >= 4")
            assert cdp.evaluate("document.body.innerText.includes('业务数据均为本地 Mock')")
            assert not cdp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            cdp.screenshot("customer-home-desktop.png")

            cdp.click(".capability-card")
            cdp.wait("document.querySelector('#detailDialog').open === true")
            assert cdp.evaluate("document.querySelector('#detailDialog').innerText.includes('MOCK')")
            cdp.screenshot("self-service-result-desktop.png")

            cdp.click("[data-dialog-human]")
            cdp.wait("document.querySelector('#progressView').classList.contains('active')")
            cdp.wait("document.querySelectorAll('.record').length >= 2")
            assert cdp.evaluate("document.body.innerText.includes('异步工单承接')")

            cdp.navigate(TARGET + "static/agent.html")
            cdp.wait("document.querySelectorAll('.case-card').length >= 1")
            cdp.click(".case-card[data-case-type='ticket']")
            cdp.wait("document.querySelector('.detail-header') !== null")
            assert cdp.evaluate("document.querySelector('#agentDetail').innerText.includes('处理操作')")
            cdp.insert_text("#agentComment", "已核验用户问题，等待业务处理。")
            cdp.click("#agentCommentForm button[type='submit']")
            cdp.wait("document.querySelector('#agentDetail').innerText.includes('已核验用户问题')")
            cdp.click("#targetStatus")
            cdp.key("ArrowDown", "ArrowDown")
            cdp.key("Enter", "Enter")
            cdp.click("#transitionBtn")
            cdp.wait("document.querySelector('#agentDetail').innerText.includes('处理中')")
            cdp.screenshot("agent-workspace-desktop.png")

            cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True,
                "screenWidth": 390, "screenHeight": 844,
            })
            cdp.navigate(TARGET)
            cdp.wait("document.querySelectorAll('.object-card').length === 3")
            assert cdp.evaluate("getComputedStyle(document.querySelector('.mobile-nav')).display === 'grid'")
            assert not cdp.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            cdp.screenshot("customer-home-mobile.png")

            if cdp.exceptions:
                raise AssertionError(f"Browser JavaScript exceptions: {cdp.exceptions}")
            print(json.dumps({
                "status": "passed",
                "checks": [
                    "desktop home/context/capabilities", "self-service dialog",
                    "human handoff and progress", "agent comment and status transition", "mobile viewport",
                    "no JavaScript exceptions", "no horizontal overflow",
                ],
                "screenshots": [str(path) for path in sorted(ARTIFACTS.glob("*.png"))],
            }, ensure_ascii=False, indent=2))
        finally:
            cdp.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
