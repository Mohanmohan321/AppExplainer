# DemoFlow marketplace

A Claude Code plugin marketplace containing the **demoflow** plugin.

---

# DemoFlow

A Claude Code plugin that produces professional, step-by-step explainer videos from real websites, web
applications and desktop software. Claude inspects the actual workflow, writes a scene plan for your approval,
generates a voice-over and synchronized captions, records the real application with Playwright (visible cursor,
smooth movement, step banners), assembles the result with FFmpeg and validates the final MP4 before reporting
done. Nothing is application-specific: you describe the workflow, DemoFlow adapts.

## Install

```
/plugin marketplace add <owner>/demoflow-marketplace
/plugin install demoflow@demoflow-marketplace
```

Then run `/demoflow` with a description, for example:

```
/demoflow Show how to create an invoice in https://app.example.com for new accounting staff, 75 seconds, British English
```

## Requirements

Python 3.9+, Playwright with Chromium (`pip install playwright && playwright install chromium`), FFmpeg (system
install, or `pip install imageio-ffmpeg`), and optionally `edge-tts` (`pip install edge-tts`, free, needs internet)
for the narration. FFmpeg built with libass is needed for burned-in captions; SRT/VTT files are always written.
The skill checks all of this first (`scripts/preflight.py`) and never installs anything without telling you.

## Safety

DemoFlow rehearses with `--dry` (no submits, no paid calls), asks before any consequential or paid action, keeps
credentials and login state out of frames, logs and Git, never bypasses CAPTCHA or other protections, and reports
failures honestly. It includes a self-test (`scripts/selftest.py`) that runs on a local throwaway page.

See `plugins/demoflow/skills/demoflow/references/` for the production workflow, recording guidelines, quality checklist and setup.