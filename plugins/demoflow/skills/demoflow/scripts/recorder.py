"""Playwright recording helper for DemoFlow. Import it from a per-video record script:

    import sys; sys.path.insert(0, "<skill>/scripts")
    from recorder import Recorder
    with Recorder("plan.json", intro={"title": "...", "subtitle": "..."}) as rec:
        rec.open("https://example.com")
        page = rec.page
        with rec.scene("intro"):
            rec.pause(2.5); rec.hide_intro()
        with rec.scene("open-form"):
            rec.click(page.get_by_role("button", name="Start"))
        with rec.scene("submit"):
            rec.click(page.get_by_role("button", name="Submit"), consequential=True)  # skipped with --dry

What it adds on top of Playwright: a visible cursor with click ripples, smooth eased mouse paths,
a scene banner, an optional intro card, a magenta sync flash (lets assemble.py align video time to the
action log), per-scene timestamps (timeline.json), failure screenshots, and --dry protection.
Nothing here knows about any particular site. Credentials: read env vars / storage_state, never print them.
"""
import json, math, sys, time
from _common import Workspace

OVERLAY_JS = r"""
(() => {
  if (window.__df) return; window.__df = true;
  const CFG = __CFG__;
  const css = `
  #df-cursor{position:fixed;left:0;top:0;width:34px;height:34px;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 3px 5px rgba(0,0,0,.45))}
  .df-ripple{position:fixed;z-index:2147483646;pointer-events:none;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;border:3px solid ${CFG.accent};background:${CFG.accent}33;animation:dfr .6s ease-out forwards}
  @keyframes dfr{to{transform:scale(4.5);opacity:0}}
  #df-banner{position:fixed;right:36px;top:22px;z-index:2147483645;pointer-events:none;display:flex;gap:12px;align-items:center;background:rgba(24,24,40,.92);color:#fff;font:700 22px 'Segoe UI',Arial,sans-serif;padding:10px 20px 10px 12px;border-radius:999px;box-shadow:0 6px 20px rgba(0,0,0,.3);opacity:0;transform:translateY(-14px);transition:opacity .45s ease,transform .45s ease}
  #df-banner.on{opacity:1;transform:none}
  #df-banner b{background:${CFG.accent};border-radius:999px;padding:5px 14px;font-size:17px;letter-spacing:.04em}
  #df-intro{position:fixed;inset:0;z-index:2147483644;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:radial-gradient(circle at 30% 20%,${CFG.accent},#1e1b3a 70%);color:#fff;font-family:'Segoe UI',Arial,sans-serif;transition:opacity .9s ease;text-align:center;padding:0 80px}
  #df-intro h1{margin:0;font-size:68px;font-weight:800} #df-intro p{margin:0;font-size:30px;opacity:.85}
  #df-intro.off{opacity:0;pointer-events:none}`;
  const init = () => {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    let html = `<div id="df-banner"><b></b><span></span></div>
      <svg id="df-cursor" viewBox="0 0 24 24"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    if (CFG.intro) html += `<div id="df-intro"><h1></h1><p></p></div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    if (CFG.intro) { const i = document.getElementById('df-intro'); i.querySelector('h1').textContent = CFG.intro.title || ''; i.querySelector('p').textContent = CFG.intro.subtitle || ''; }
    const cur = document.getElementById('df-cursor');
    document.addEventListener('mousemove', e => { cur.style.transform = `translate(${e.clientX-4}px,${e.clientY-2}px)`; }, true);
    document.addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = 'df-ripple'; r.style.left = e.clientX+'px'; r.style.top = e.clientY+'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
  };
  if (document.body) init(); else document.addEventListener('DOMContentLoaded', init);
  window.__dfBanner = (label, title) => { const b = document.getElementById('df-banner'); if (!b) return; b.classList.remove('on');
    if (!label && !title) return;
    setTimeout(() => { b.querySelector('b').textContent = label; b.querySelector('span').textContent = title; b.classList.add('on'); }, 250); };
  window.__dfIntro = on => document.getElementById('df-intro')?.classList.toggle('off', !on);
})();
"""


def _ease(t):
    return t * t * (3 - 2 * t)


class Recorder:
    def __init__(self, plan_path, headless=True, storage_state=None, dry=None, accent="#7c3aed",
                 intro=None, banner=True, context_options=None):
        self.ws = Workspace(plan_path)
        v = self.ws.plan["video"]
        self.W, self.H = v["width"], v["height"]
        self.dry = ("--dry" in sys.argv) if dry is None else dry
        self.headless, self.storage_state = headless, storage_state
        self.accent, self.intro, self.banner = accent, intro, banner
        self.context_options = context_options or {}
        self.tts = {}
        p = self.ws.work / "tts.json"
        if p.exists():
            self.tts = {e["id"]: e for e in json.loads(p.read_text(encoding="utf-8"))}
        else:
            print("warning: tts.json missing - run tts.py first so scenes hold for the narration length")
        numbered = [s["id"] for s in self.ws.scenes if s.get("numbered", True) and not s.get("label")]
        self._num = {sid: i + 1 for i, sid in enumerate(numbered)}
        self._total = len(numbered)
        self.timeline, self.sync_t, self.page = [], None, None
        self.x, self.y, self.t0 = self.W / 2, self.H / 2, None

    # ---- lifecycle -------------------------------------------------------
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless, args=["--hide-scrollbars"])
        raw = self.ws.work / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        for f in raw.glob("*.webm"):
            f.unlink()
        opts = dict(viewport={"width": self.W, "height": self.H}, record_video_dir=str(raw),
                    record_video_size={"width": self.W, "height": self.H}, **self.context_options)
        if self.storage_state:
            opts["storage_state"] = str(self.storage_state)
        self.ctx = self.browser.new_context(**opts)
        cfg = json.dumps({"accent": self.accent, "intro": self.intro})
        self.ctx.add_init_script(OVERLAY_JS.replace("__CFG__", cfg))
        self.page = self.ctx.new_page()
        self.t0 = time.monotonic()
        return self

    def __exit__(self, et, ev, tb):
        ok = et is None
        vpath = None
        try:
            if ok:
                self.pause(0.6)
            vpath = self.page.video.path()
            self.ctx.close()
            self.browser.close()
            self._pw.stop()
        except Exception as e:
            print("warning: closing recorder:", e)
        if ok and vpath:
            (self.ws.work / "timeline.json").write_text(json.dumps(
                {"timeline": self.timeline, "video": str(vpath), "sync_t": self.sync_t}, indent=1), encoding="utf-8")
            print(f"recorded {vpath}")
        elif not ok:
            print("recording FAILED - timeline.json not written (a stale one may exist; do not assemble it)")
        return False

    def now(self):
        return time.monotonic() - self.t0

    # ---- page + scenes ---------------------------------------------------
    def open(self, url, wait_until="networkidle", settle=1.0):
        """Navigate, then flash the sync marker once the page is ready."""
        self.page.goto(url, wait_until=wait_until)
        self.page.wait_for_timeout(int(settle * 1000))
        self.page.mouse.move(self.x, self.y)
        self.page.wait_for_timeout(800)
        self.sync_t = self.now()
        self.page.evaluate("""() => { const d = document.createElement('div');
          d.style.cssText = 'position:fixed;inset:0;background:#ff00ff;z-index:2147483647';
          document.body.appendChild(d); setTimeout(() => d.remove(), 700); }""")
        self.page.wait_for_timeout(1200)

    def scene(self, sid, hold=True):
        return _Scene(self, sid, hold)

    def hide_intro(self):
        self.page.evaluate("window.__dfIntro(false)")

    def pause(self, seconds):
        time.sleep(seconds)

    def screenshot(self, name):
        p = self.ws.work / f"{name}.png"
        self.page.screenshot(path=str(p))
        return p

    # ---- visible interaction --------------------------------------------
    def move(self, x, y, dur=None):
        dist = math.hypot(x - self.x, y - self.y)
        dur = dur or min(1.1, max(0.5, 0.35 + dist / 1800))
        n = max(8, int(dur * 50))
        x0, y0 = self.x, self.y
        nx, ny = -(y - y0) / (dist or 1), (x - x0) / (dist or 1)
        for i in range(1, n + 1):
            t = _ease(i / n)
            arc = math.sin(math.pi * t) * dist * 0.05
            self.page.mouse.move(x0 + (x - x0) * t + nx * arc, y0 + (y - y0) * t + ny * arc)
            time.sleep(dur / n)
        self.x, self.y = x, y

    def reveal(self, loc, block="center"):
        loc.evaluate(f"e => e.scrollIntoView({{behavior:'smooth', block:'{block}'}})")
        self.page.wait_for_timeout(900)

    def hover(self, loc, scroll=True, dx=0, dy=0):
        if scroll:
            self.reveal(loc)
        b = loc.bounding_box()
        self.move(b["x"] + b["width"] / 2 + dx, b["y"] + b["height"] / 2 + dy)

    def click(self, loc, scroll=True, consequential=False):
        """Move, then click. consequential=True (submits, purchases, deletes, paid generation)
        is skipped under --dry so rehearsals never change real state or spend money."""
        self.hover(loc, scroll)
        self.page.wait_for_timeout(250)
        if consequential and self.dry:
            print("  [dry] skipped consequential click")
            return False
        self.page.mouse.down()
        self.page.wait_for_timeout(70)
        self.page.mouse.up()
        self.page.wait_for_timeout(450)
        return True

    def type_text(self, loc, text, delay=70, clear=True):
        """Click the field and type with visible keystrokes. Never type real secrets on camera:
        authenticate off-camera (storage_state) and keep password fields out of the recording."""
        self.click(loc)
        if clear:
            self.page.keyboard.press("Control+A")
        self.page.keyboard.type(text, delay=delay)
        self.page.wait_for_timeout(400)

    def upload(self, trigger, file_path, input_locator=None):
        """Put the cursor on the upload control, then attach the file (file chooser, else direct input)."""
        self.hover(trigger)
        try:
            with self.page.expect_file_chooser(timeout=4000) as fc:
                self.page.mouse.down()
                self.page.wait_for_timeout(70)
                self.page.mouse.up()
            fc.value.set_files(str(file_path))
        except Exception:
            if input_locator is None:
                raise
            input_locator.set_input_files(str(file_path))
        self.page.wait_for_timeout(1500)

    def wait_until(self, predicate, timeout=300, poll=2.0, desc="condition", log=True):
        """Poll a Python callable until truthy. Raises TimeoutError - never assume success."""
        start, last = time.monotonic(), None
        while time.monotonic() - start < timeout:
            v = predicate()
            if log and v != last:
                print(f"  {desc}: {v}")
                last = v
            if v:
                return v
            time.sleep(poll)
        raise TimeoutError(f"{desc} not met within {timeout}s")


class _Scene:
    def __init__(self, rec, sid, hold):
        self.rec, self.sid, self.hold = rec, sid, hold
        self.meta = next((s for s in rec.ws.scenes if s["id"] == sid), None)
        if self.meta is None:
            raise KeyError(f"scene '{sid}' is not in plan.json")

    def __enter__(self):
        r = self.rec
        self.t0 = r.now()
        label = self.meta.get("label") or (f"STEP {r._num[self.sid]}/{r._total}" if self.sid in r._num else "")
        if r.banner and self.meta.get("banner", True):
            r.page.evaluate("([l,t]) => window.__dfBanner(l,t)", [label, self.meta.get("title", "")])
        print(f"[{self.t0:6.1f}s] {self.sid}")
        return self

    def __exit__(self, et, ev, tb):
        r = self.rec
        if et:
            try:
                r.page.screenshot(path=str(r.ws.work / f"fail_{self.sid}.png"))
            except Exception:
                pass
            return False
        t = r.ws.plan["timing"]
        need = r.tts.get(self.sid, {}).get("duration", 3.0) + t["lead"] + t["tail"]
        spent = r.now() - self.t0
        if self.hold and spent < need:
            time.sleep(need - spent)
        r.timeline.append({"id": self.sid, "t0": self.t0, "t1": r.now()})
        return False
