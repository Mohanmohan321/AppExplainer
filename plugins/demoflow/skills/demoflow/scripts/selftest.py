"""End-to-end self-test of the DemoFlow pipeline against a throwaway LOCAL page (no external sites,
no paid calls). Default TTS is 'silent'; pass --tts edge-tts to also exercise the real engine (network).

  python selftest.py [--tts silent|edge-tts] [--keep]
Runs: tts -> record -> assemble -> validate in a temp workspace and fails loudly if any stage fails.
"""
import argparse, functools, http.server, json, os, pathlib, shutil, subprocess, sys, tempfile, threading

HERE = pathlib.Path(__file__).resolve().parent
PAGE = """<!doctype html><meta charset=utf-8><title>Selftest</title>
<body style="font:20px Segoe UI,Arial;margin:80px;background:#fafafa">
<h1>Sample form</h1>
<label>Name <input id=name style="font-size:20px;padding:8px"></label>
<button id=go style="font-size:20px;padding:10px 24px;margin-left:12px">Generate</button>
<p id=status>Idle</p><div id=result style="display:none;padding:40px;background:#dff5e1;border-radius:12px;margin-top:20px">Result ready</div>
<script>const st=document.getElementById('status'),res=document.getElementById('result');document.getElementById('go').onclick=()=>{st.textContent='Working...';setTimeout(()=>{st.textContent='Done';res.style.display='block'},3500)}</script>"""

RECORD = """
import sys, pathlib
sys.path.insert(0, %(scripts)r)
from recorder import Recorder
HERE = pathlib.Path(__file__).resolve().parent
with Recorder(HERE / "plan.json", intro={"title": "Selftest", "subtitle": "local page"}) as rec:
    page = rec.page
    rec.open(%(url)r)
    with rec.scene("intro"):
        rec.pause(1.5); rec.hide_intro()
    with rec.scene("type"):
        rec.type_text(page.locator("#name"), "Demo user")
    with rec.scene("go"):
        rec.click(page.locator("#go"), consequential=True)
    with rec.scene("wait"):
        rec.wait_until(lambda: page.locator("#result").is_visible(), timeout=30, poll=0.5, desc="result visible")
    with rec.scene("result"):
        rec.reveal(page.locator("#result")); rec.screenshot("final_state")
"""


def step(title, cmd, cwd):
    print(f"\n=== {title}")
    r = subprocess.run(cmd, cwd=cwd, text=True)
    if r.returncode:
        raise SystemExit(f"SELFTEST FAILED at: {title}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tts", default="silent", choices=["silent", "edge-tts"]); ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="demoflow-selftest-"))
    site = tmp / "site"; site.mkdir(); (site / "index.html").write_text(PAGE, encoding="utf-8")
    ws = tmp / "ws"; ws.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *args, **kw: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    plan = {"title": "Selftest", "basename": "selftest", "tts": {"engine": a.tts}, "video": {"width": 1280, "height": 720, "fps": 30, "crf": 23, "preset": "veryfast"},
            "scenes": [
                {"id": "intro", "title": "Intro", "label": "INTRO", "narration": "This is a self test of the demo pipeline."},
                {"id": "type", "title": "Type a name", "narration": "First, type a name into the field."},
                {"id": "go", "title": "Generate", "narration": "Then click Generate."},
                {"id": "wait", "title": "Waiting", "narration": "We speed up the wait.", "speed_up_to": 3},
                {"id": "result", "title": "Result", "label": "DONE", "narration": "And the result appears."}]}
    (ws / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    (ws / "record.py").write_text(RECORD % {"scripts": str(HERE), "url": url}, encoding="utf-8")
    py, P = sys.executable, str(ws / "plan.json")
    try:
        step("tts", [py, str(HERE / "tts.py"), "--plan", P], ws)
        step("tts again (must hit cache)", [py, str(HERE / "tts.py"), "--plan", P], ws)
        step("record (real click: page is local and harmless)", [py, "record.py"], ws)
        step("assemble", [py, str(HERE / "assemble.py"), "--plan", P], ws)
        step("validate", [py, str(HERE / "validate.py"), "--plan", P], ws)
    finally:
        srv.shutdown()
    print(f"\nSELFTEST PASSED. workspace: {tmp}" + ("" if a.keep else "  (deleted)"))
    if not a.keep: shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
