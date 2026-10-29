# Setup, usage, and dependencies

## Install
The skill is the folder `.claude/skills/demoflow/` (project-level). To use it in every project, copy the folder
to `~/.claude/skills/demoflow/`. Claude Code discovers `SKILL.md` automatically; invoke with `/demoflow ...` or
let it trigger from a request such as "make a tutorial video of ...".

## Dependencies (check with `python scripts/preflight.py`)
| Need | Required? | Install / alternative |
|---|---|---|
| Python 3.9+ | yes | python.org |
| Playwright (Python) + Chromium | yes for browser apps | `pip install playwright && playwright install chromium` |
| FFmpeg | yes | system install, or `pip install imageio-ffmpeg` (bundled binary; `ffprobe` not included) |
| FFmpeg with libass (`subtitles` filter) | for burned-in captions | full build (gyan.dev / BtbN / package manager); otherwise sidecar SRT/VTT only |
| ffprobe | optional | ships with full FFmpeg; `validate.py` falls back to parsing `ffmpeg -i` |
| `edge-tts` | optional TTS engine | `pip install edge-tts` (free, needs internet to Microsoft's service). Alternatives: `tts.engine: "command"` (any CLI, e.g. a local TTS) or `"silent"` for rehearsals |
Nothing else is needed. The scripts never install anything themselves.

## Typical session
```
python <skill>/scripts/preflight.py --init demoflow/my-video      # check tools, scaffold workspace
# edit demoflow/my-video/plan.json (scenes, narration, voice) and record.py (locators)
cd demoflow/my-video
set DEMOFLOW_SCRIPTS=<skill>/scripts                               # PowerShell: $env:DEMOFLOW_SCRIPTS="..."
python <skill>/scripts/tts.py      --plan plan.json
python record.py --dry                                             # rehearsal, no consequential clicks
python record.py                                                   # real take (after approval)
python <skill>/scripts/assemble.py --plan plan.json
python <skill>/scripts/validate.py --plan plan.json
```
Self-test of the toolchain (local page, no external sites, no cost): `python <skill>/scripts/selftest.py`
(add `--tts edge-tts` to also test the real voice engine; `--keep` to keep the temp workspace).

## Voices, language, pace
`python tts.py --list-voices --lang en-GB` lists edge-tts voices. In plan.json set `language`, `tts.voice`,
`tts.rate` (`-10%` slower), `tts.pitch`, `tts.pronunciations`. Another language needs a matching voice and
narration text in that language; captions follow the narration text.

## Other formats
- Vertical/social (**untested** - the self-test only covers 1280x720 and 1920x1080-style landscape): `video.width/height` = 1080x1920 and pass `context_options={"is_mobile": True, "has_touch": True}`
  to `Recorder` (and design the app state for a narrow viewport).
- Existing screen recording instead of Playwright: write `work/timeline.json` by hand (see recording-guidelines.md).
  The assemble step with a hand-made timeline (`sync_t: null`) was tested on a Playwright WebM; other source
  formats should work through ffmpeg but were not tested.
- Music: `"music": {"file": "assets/track.mp3", "volume": 0.08}` - only user-provided or licensed audio.

## Example invocations
1. `/demoflow Show how to create an invoice in https://app.example.com for new accounting staff, 75 seconds, British English`
2. `/demoflow Checkout walkthrough of our staging shop (login in .env.staging), 1080x1920 for social, no music, upbeat voice`
3. `/demoflow Narrate and caption my existing recording ./raw/export.mp4 explaining the export feature, Spanish voice`
4. `/demoflow Create the plan only for onboarding a new user in our admin portal; I will review before any recording`

## Troubleshooting
- "scenes not recorded": the recording failed or `plan.json` scenes changed after recording; re-record.
- Output much longer/shorter than expected: check `work/assemble_report.json`; validate flags duration mismatches.
- Captions not burned in: your ffmpeg lacks libass; use the SRT/VTT or install a full build.
- Locator timeouts: open `work/fail_<scene>.png`; the UI state differs from what you assumed.
