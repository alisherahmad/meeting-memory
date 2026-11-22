"""Accessibility checks for the web UI (src/meeting_memory/static).

Two layers:
1. Static checks, always run: colour-token contrast in both schemes, ARIA wiring
   in index.html, and the element ids app.js depends on.
2. A keyboard and announcement test in headless Chrome/Edge over the DevTools
   protocol. It skips when no browser or the `websockets` package is available.
   No API key is used: /api/ask is answered from a canned stream by intercepting
   the request in the browser, so the drawer can be opened from a real citation.
"""
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "meeting_memory" / "static"


# ---------------------------------------------------------------- contrast ---
def _lum(hex_):
    h = hex_.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _themes():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    light_block = re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
    dark_block = re.search(r"prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.S).group(1)
    tok = lambda block: {k: v.lower() for k, v in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block)}
    light = tok(light_block)
    return {"light": light, "dark": {**light, **tok(dark_block)}}


# (foreground, background, minimum): text pairs need 4.5:1 (WCAG 1.4.3);
# control boundaries and the focus ring need 3:1 (WCAG 1.4.11).
PAIRS = [
    ("ink", "paper", 4.5), ("ink-2", "paper", 4.5), ("ink-2", "surface", 4.5),
    ("ink-3", "paper", 4.5), ("ink-3", "surface", 4.5),
    ("accent", "paper", 4.5), ("accent", "surface", 4.5), ("accent-ink", "accent", 4.5),
    ("current", "current-bg", 4.5), ("open", "open-bg", 4.5), ("gone", "gone-bg", 4.5),
    ("accent", "gone-bg", 4.5), ("info", "info-bg", 4.5), ("info", "surface", 4.5),
    ("control-border", "paper", 3.0), ("control-border", "surface", 3.0),
]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_token_contrast_meets_wcag_aa(theme):
    t = _themes()[theme]
    failures = [f"{fg} on {bg}: {_ratio(t[fg], t[bg]):.2f} < {need}"
                for fg, bg, need in PAIRS if _ratio(t[fg], t[bg]) < need]
    assert not failures, failures


def test_controls_use_control_border_not_divider_token():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for sel in ("textarea, select {", ".segmented {", "button.ghost {", ".chip-cite {"):
        rule = css[css.index(sel):].split("}", 1)[0]
        assert "var(--control-border)" in rule, sel
    # Overflow on the segmented group would clip focus rings.
    seg = css[css.index(".segmented {"):].split("}", 1)[0]
    assert "overflow" not in seg
    # De-emphasis by opacity drops text below AA; the future-meeting cards must not use it.
    fut = css[css.index(".meeting-card.future {"):].split("}", 1)[0]
    assert "opacity" not in fut


# ------------------------------------------------------------------- HTML ---
class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.by_id[a["id"]] = (tag, a)


def _html():
    p = _Collect()
    p.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    return p.by_id


REQUIRED_IDS = ("status q q-error ask-team examples ask-btn trace answer mem-team asof mem-filter meetings-strip "
                "threads brief-form brief-team brief-before brief-llm brief-btn brief drawer drawer-title "
                "drawer-body drawer-close scrim announcer alerter").split()


def test_index_keeps_ids_app_js_depends_on():
    ids = _html()
    missing = [i for i in REQUIRED_IDS if i not in ids]
    assert not missing, missing


def test_dialog_and_live_region_wiring():
    ids = _html()
    tag, drawer = ids["drawer"]
    assert drawer.get("role") == "dialog" and drawer.get("aria-modal") == "true"
    assert drawer.get("aria-labelledby") == "drawer-title"
    assert ids["drawer-body"][1].get("tabindex") == "0"  # scrollable region reachable by keyboard
    assert ids["announcer"][1].get("role") == "status" and ids["announcer"][1].get("aria-live") == "polite"
    assert ids["alerter"][1].get("role") == "alert"
    # Results panels are not live regions: announcing them reads every citation and the cost line.
    for quiet in ("status", "answer", "trace", "brief", "threads"):
        assert "aria-live" not in ids[quiet][1], quiet
    for busy in ("answer", "brief", "threads", "drawer-body"):
        assert ids[busy][1].get("aria-busy") == "false", busy
    for group in ("asof", "mem-filter"):
        assert ids[group][1].get("role") == "radiogroup" and ids[group][1].get("aria-labelledby"), group


# ------------------------------------------------------- browser (keyboard) ---
def _find_browser():
    env = os.environ.get("MM_TEST_BROWSER")
    cands = [env] if env else []
    cands += [shutil.which(n) for n in ("chrome", "google-chrome", "chromium", "msedge")]
    cands += [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next((c for c in cands if c and Path(c).exists()), None)


class _CDP:
    def __init__(self, url):
        from websockets.sync.client import connect
        self.ws = connect(url, max_size=None)
        self.n = 0
        self.events = []

    def send(self, method, params=None, session=None):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        while True:
            r = json.loads(self.ws.recv(timeout=20))
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})
            if "method" in r:
                self.events.append(r)

    def wait_event(self, name, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            for e in self.events:
                if e["method"] == name:
                    self.events.remove(e)
                    return e
            try:
                r = json.loads(self.ws.recv(timeout=0.5))
                if "method" in r:
                    self.events.append(r)
            except TimeoutError:
                pass
        raise TimeoutError(name)


KEYS = {"Tab": 9, "Enter": 13, "Escape": 27, " ": 32, "End": 35, "Home": 36,
        "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40}


class _Page:
    def __init__(self, cdp, session):
        self.cdp, self.s = cdp, session

    def js(self, expr):
        r = self.cdp.send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True}, self.s)
        if "exceptionDetails" in r:
            raise AssertionError(r["exceptionDetails"])
        return r["result"].get("value")

    def key(self, key, shift=False):
        base = {"key": key, "code": "Space" if key == " " else key, "windowsVirtualKeyCode": KEYS[key],
                "modifiers": 8 if shift else 0}
        text = {"Enter": "\r", " ": " "}.get(key)
        self.cdp.send("Input.dispatchKeyEvent", {**base, "type": "keyDown", **({"text": text} if text else {})}, self.s)
        self.cdp.send("Input.dispatchKeyEvent", {**base, "type": "keyUp"}, self.s)

    def wait(self, expr, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expr):
                return
            time.sleep(0.05)
        raise AssertionError(f"timed out waiting for: {expr}")

    def active(self):
        return self.js("(() => { const a = document.activeElement; return a ? (a.id || a.className || a.tagName) + '|' + (a.textContent || '').trim().slice(0, 40) : null })()")


@pytest.fixture
def live_server(settings, monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    from conftest import MEETING_A, MEETING_B
    from meeting_memory.ingest import run_ingest
    from meeting_memory.llm import LLM
    from meeting_memory.server import create_app
    from meeting_memory.store import Store

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    d = Path(settings.transcripts_dir)
    d.mkdir(parents=True)
    (d / "ZZ0001a.txt").write_text(MEETING_A, encoding="utf-8")
    (d / "ZZ0001b.txt").write_text(MEETING_B, encoding="utf-8")
    store = Store(settings.db_path)
    run_ingest(settings, store, LLM(settings, store), on_event=lambda s: None)
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    end = time.time() + 15
    while not server.started and time.time() < end:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture
def page(live_server):
    pytest.importorskip("websockets")
    exe = _find_browser()
    if not exe:
        pytest.skip("no Chrome/Edge found (set MM_TEST_BROWSER)")
    prof = tempfile.mkdtemp(prefix="mm-a11y-")
    proc = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={prof}",
                             "--no-first-run", "--no-default-browser-check", "--disable-gpu", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        port_file = Path(prof) / "DevToolsActivePort"
        end = time.time() + 20
        while not (port_file.exists() and port_file.read_text().count("\n") >= 1) and time.time() < end:
            time.sleep(0.1)
        port, path = port_file.read_text().split()[:2]
        cdp = _CDP(f"ws://127.0.0.1:{port}{path}")
        target = cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        p = _Page(cdp, session)
        cdp.send("Page.enable", {}, session)
        cdp.send("Page.navigate", {"url": live_server + "/#ask"}, session)
        p.wait("document.querySelectorAll('#ask-team option').length > 1", 15)
        yield p
    finally:
        proc.kill()
        proc.wait(timeout=10)
        shutil.rmtree(prof, ignore_errors=True)


CANNED_RESULT = {
    "state": "answered", "answer": "They chose solar cells first, then a rechargeable battery.",
    "citations": [{"meeting_id": "ZZ0001a", "turn": 3, "speaker": "A", "time": "00:00:30",
                   "quote": "for now we go with solar cells as the energy source", "method": "exact"}],
    "steps": 3, "tool_calls": 2, "seconds": 1.2, "usage": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0},
}


def test_keyboard_and_announcements(page):
    p = page
    announcer = "document.querySelector('#announcer').textContent"
    alerter = "document.querySelector('#alerter').textContent"

    # --- Ask: validation error is tied to the field and focus moves to it.
    p.js("document.querySelector('#ask-btn').focus()")
    p.key("Enter")
    p.wait("document.activeElement.id === 'q'")
    assert p.js("document.querySelector('#q').getAttribute('aria-invalid')") == "true"
    assert p.js("document.querySelector('#q').getAttribute('aria-describedby')") == "q-error"
    assert p.js("!document.querySelector('#q-error').hidden && document.querySelector('#q-error').textContent.length > 0")
    p.cdp.send("Input.insertText", {"text": "Team ZZ0001: what energy source did they choose?"}, p.s)
    assert p.js("document.querySelector('#q').hasAttribute('aria-invalid')") is False
    assert p.js("document.querySelector('#q').hasAttribute('aria-describedby')") is False

    # --- Ask failure (no API key, server answers 503): announced assertively,
    # busy state cleared, focus stays on the button.
    p.js("document.querySelector('#ask-btn').focus()")
    p.key("Enter")
    p.wait(f"{alerter}.startsWith('Question failed')")
    p.wait("document.querySelector('#ask-btn').getAttribute('aria-disabled') === 'false'")
    assert p.js("document.querySelector('#answer').getAttribute('aria-busy')") == "false"
    assert p.js("document.activeElement.id") == "ask-btn"

    # --- Ask success: a canned stream with one citation. Polite summary only.
    p.cdp.send("Fetch.enable", {"patterns": [{"urlPattern": "*/api/ask*"}]}, p.s)
    p.key("Enter")
    paused = p.cdp.wait_event("Fetch.requestPaused")
    body = ('event: trace\ndata: {"step": 1, "kind": "note", "detail": "searching"}\n\n'
            f"event: result\ndata: {json.dumps(CANNED_RESULT)}\n\n")
    p.cdp.send("Fetch.fulfillRequest", {"requestId": paused["params"]["requestId"], "responseCode": 200,
                                         "responseHeaders": [{"name": "Content-Type", "value": "text/event-stream"}],
                                         "body": base64.b64encode(body.encode()).decode()}, p.s)
    p.cdp.send("Fetch.disable", {}, p.s)
    p.wait(f"{announcer} === 'Answer ready, answered, 1 verified citation.'")
    assert p.js("document.querySelector('#answer').getAttribute('aria-busy')") == "false"

    # --- Transcript drawer: modal, focus trapped, Escape closes, focus restored.
    p.js("document.querySelector('.cite').focus()")
    p.key("Enter")
    p.wait("document.querySelector('#drawer').getAttribute('aria-hidden') === 'false'")
    p.wait("document.querySelector('#drawer-body').getAttribute('aria-busy') === 'false'")
    assert p.js("document.querySelector('#drawer').contains(document.activeElement)")
    assert p.js("['header.masthead','nav.tabs','main'].every(s => document.querySelector(s).inert)")
    assert p.js("!!document.querySelector('#target-turn mark')")  # quote highlighted in its turn
    for shift in (False, False, False, True, True, True):
        p.key("Tab", shift=shift)
        assert p.js("document.querySelector('#drawer').contains(document.activeElement)"), p.active()
    p.js("document.querySelector('#ask-btn').focus()")  # background is inert: focus must not move there
    assert p.js("document.querySelector('#drawer').contains(document.activeElement)")
    p.key("Escape")
    p.wait("document.querySelector('#drawer').getAttribute('aria-hidden') === 'true'")
    assert p.js("['header.masthead','nav.tabs','main'].every(s => !document.querySelector(s).inert)")
    assert p.js("document.activeElement.classList.contains('cite')"), p.active()

    # --- Tabs by keyboard, then the Memory radio groups.
    p.js("document.querySelector('#tab-ask').focus()")
    p.key("ArrowRight")
    p.wait("!document.querySelector('#view-memory').hidden")
    p.js("document.querySelector('#mem-team').value = 'ZZ0001'; document.querySelector('#mem-team').dispatchEvent(new Event('change'))")
    p.wait("document.querySelectorAll('#mem-filter [role=radio]').length === 4 && document.querySelector('#threads').getAttribute('aria-busy') === 'false'")
    p.wait(f"{announcer}.startsWith('ZZ0001') || {announcer}.startsWith('No extracted memory for ZZ0001')")
    for group in ("#asof", "#mem-filter"):
        assert p.js(f"document.querySelectorAll('{group} [tabindex=\"0\"]').length") == 1, group
    # Tab moves between groups, not through every option.
    p.js("document.querySelector('#asof [aria-checked=true]').focus()")
    p.key("Tab")
    assert p.js("document.activeElement.closest('#mem-filter') && document.activeElement.getAttribute('aria-checked') === 'true'"), p.active()

    checked = "document.querySelector('#mem-filter [aria-checked=true]').textContent"
    in_filter_and_checked = "document.activeElement.closest('#mem-filter') && document.activeElement.getAttribute('aria-checked') === 'true'"
    for key, expect in (("ArrowRight", "changed"), ("End", "open disputes"), ("ArrowRight", "all"),
                        ("ArrowLeft", "open disputes"), ("Home", "all")):
        p.key(key)
        p.wait(f"{checked} === '{expect}'")
        p.wait("document.querySelector('#threads').getAttribute('aria-busy') === 'false'")
        # Focus survives the re-render that follows each pick.
        assert p.js(in_filter_and_checked), (key, p.active())
        assert p.js("document.querySelectorAll('#mem-filter [tabindex=\"0\"]').length") == 1

    # --- Brief (deterministic): busy and outcome announced; focus kept on the button.
    p.js("document.querySelector('#tab-brief').click()")
    p.js("document.querySelector('#brief-team').value = 'ZZ0001'; document.querySelector('#brief-team').dispatchEvent(new Event('change'))")
    p.js("document.querySelector('#brief-llm').focus()")
    p.key(" ")
    assert p.js("document.querySelector('#brief-llm').checked") is False
    p.js("document.querySelector('#brief-btn').focus()")
    p.key("Enter")
    p.wait(f"/^Brief ready for ZZ0001b: \\d+ cited points?\\.$/.test({announcer})")
    assert p.js("document.querySelector('#brief').getAttribute('aria-busy')") == "false"
    assert p.js("document.activeElement.id") == "brief-btn"
