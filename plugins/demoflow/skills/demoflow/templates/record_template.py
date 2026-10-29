"""Per-video recording script (copy of DemoFlow's template). EDIT the TODOs for the real workflow.

Run from this directory, after tts.py:
    python record.py --dry     # rehearsal: consequential clicks are skipped (no submits, no paid calls)
    python record.py           # real take (only after the user approved consequential actions)

The skill's scripts folder is found via the DEMOFLOW_SCRIPTS env var, or edit SKILL_SCRIPTS below.
Credentials: never hard-code. Read env vars (os.environ["APP_USER"]) or reuse a storage_state file
kept under work/ (git-ignored). Log in OFF camera (a separate login step that saves the state file).
"""
import os, pathlib, sys

SKILL_SCRIPTS = os.environ.get("DEMOFLOW_SCRIPTS", "")  # e.g. ".claude/skills/demoflow/scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from recorder import Recorder  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
START_URL = "https://example.com"                 # TODO
STATE = HERE / "work" / "auth.state.json"          # optional saved login (git-ignored)


def main():
    with Recorder(PLAN, storage_state=STATE if STATE.exists() else None,
                  intro={"title": "TODO title", "subtitle": "TODO subtitle"}) as rec:
        page = rec.page
        rec.open(START_URL)

        with rec.scene("intro"):
            rec.pause(2.5)
            rec.hide_intro()

        with rec.scene("step-one"):
            # TODO: use role/label locators; avoid brittle CSS. rec.click() moves the cursor first.
            rec.click(page.get_by_role("link", name="More information"))

        with rec.scene("submit"):
            # consequential=True -> skipped under --dry
            rec.click(page.get_by_role("button", name="Submit"), consequential=True)

        with rec.scene("wait"):
            # Poll for the real result; raises TimeoutError instead of assuming success.
            rec.wait_until(lambda: page.locator("#result").count() > 0, timeout=300, desc="result visible")

        with rec.scene("result"):
            rec.reveal(page.locator("#result"))
            rec.screenshot("final_state")   # evidence that the end state really appeared


if __name__ == "__main__":
    main()
