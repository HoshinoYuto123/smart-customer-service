"""Real-browser smoke test for the standalone key-interaction prototype."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse

import requests

from ui_cdp_smoke import ARTIFACTS, CHROME, CDP, free_port


def main() -> None:
    prototype = (
        ARTIFACTS.parents[1]
        / "docs"
        / "prototypes"
        / "customer-service-key-interactions.html"
    ).resolve()
    if not prototype.exists():
        raise SystemExit(f"Prototype not found: {prototype}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    profile = ARTIFACTS / f"prototype-profile-{port}"
    profile.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["NO_PROXY"] = "127.0.0.1,localhost"
    process = subprocess.Popen(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-allow-origins=*",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    cdp = None
    try:
        version_url = f"http://127.0.0.1:{port}/json/version"
        for _ in range(80):
            try:
                requests.get(version_url, timeout=0.3).raise_for_status()
                break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            raise AssertionError("Chrome debugging endpoint did not start")

        file_url = prototype.as_uri()
        target_url = (
            f"http://127.0.0.1:{port}/json/new?"
            f"{urllib.parse.quote(file_url, safe=':/?=&')}"
        )
        target = requests.put(target_url, timeout=3).json()
        cdp = CDP(target["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        cdp.navigate(file_url)
        cdp.wait("document.querySelectorAll('.flow-step').length === 6")
        assert cdp.evaluate("document.querySelector('.flow-step.active').dataset.step === '0'")
        assert not cdp.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        cdp.screenshot("key-interaction-prototype-desktop.png")

        cdp.click(".quick-card[data-next]")
        cdp.wait("document.querySelector('.flow-step.active').dataset.step === '1'")
        cdp.click("#confirmCheck")
        assert cdp.evaluate("document.querySelector('#confirmRefund').disabled === false")
        cdp.click("#confirmRefund")
        cdp.wait("document.querySelector('.flow-step.active').dataset.step === '2'")

        cdp.click("#unresolvedButton")
        assert cdp.evaluate(
            "document.querySelector('.rule-meter').innerText.includes('1 / 2')"
        )
        cdp.click("#unresolvedButton")
        cdp.wait("document.querySelector('.flow-step.active').dataset.step === '3'")
        cdp.click("[data-next]")
        cdp.wait("document.querySelector('.flow-step.active').dataset.step === '4'")

        cdp.click("#agentAction")
        cdp.wait("document.querySelector('.status').innerText === '处理中'")
        cdp.click("#agentAction")
        cdp.wait("document.querySelector('.status').innerText === '待用户确认'")
        cdp.click("#agentAction")
        cdp.wait("document.querySelector('.flow-step.active').dataset.step === '5'")
        cdp.click("[data-rating='5']")
        assert cdp.evaluate("document.querySelector('#resolved').disabled === false")
        cdp.click("#resolved")
        cdp.wait("document.querySelector('#resolutionToast').innerText.includes('闭环完成')")

        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 390,
                "height": 844,
                "deviceScaleFactor": 1,
                "mobile": True,
                "screenWidth": 390,
                "screenHeight": 844,
            },
        )
        cdp.navigate(file_url)
        cdp.wait("document.querySelectorAll('.flow-step').length === 6")
        assert not cdp.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        cdp.screenshot("key-interaction-prototype-mobile.png")
        if cdp.exceptions:
            raise AssertionError(f"Browser JavaScript exceptions: {cdp.exceptions}")

        print(
            json.dumps(
                {
                    "status": "passed",
                    "checks": [
                        "six-step navigation",
                        "refund confirmation",
                        "two unresolved reports",
                        "async handoff",
                        "agent status progression",
                        "five-star resolution",
                        "desktop/mobile no horizontal overflow",
                        "no JavaScript exceptions",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        if cdp is not None:
            cdp.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
