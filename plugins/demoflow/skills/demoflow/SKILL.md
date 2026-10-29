---
name: demoflow
description: Produce a professional step-by-step explainer/tutorial video from a real website, web app, or desktop app - scene plan, voice-over, captions, recorded real workflow, FFmpeg assembly, and validation. Use when the user wants a demo video, product walkthrough, how-to/tutorial video, screen recording with narration, or captioned explainer of a real UI workflow. Works for any app; nothing is hard-coded.
argument-hint: "[what to demo] [target URL/app] [audience, length, language, voice, assets...]"
---

# DemoFlow

Turn a real UI workflow into a polished, narrated, captioned video. You orchestrate; bundled scripts do the
mechanical work. **Everything shown must be real and verified** - never invent features, fabricate results,
or claim a stage succeeded without evidence.

Bundled files (paths relative to this skill; use `${CLAUDE_SKILL_DIR}`, and if that is not expanded in your
session, resolve the folder that contains this SKILL.md, e.g. `.claude/skills/demoflow` or `~/.claude/skills/demoflow`):
- `scripts/preflight.py` - inspect tools (never installs); `--init DIR` scaffolds a workspace without overwriting.
- `scripts/tts.py` - narration (engines: `edge-tts`, `command`, `silent`), hash-cached, word-timed captions.
- `scripts/recorder.py` - Playwright helper: visible cursor, smooth moves, banners, sync flash, `--dry`.
- `scripts/assemble.py` - cut scenes, speed up waits, captions (SRT/VTT/burned), narration, fades -> MP4.
- `scripts/validate.py` - ffprobe/ffmpeg checks + evidence frames + contact sheet.
- `scripts/selftest.py` - end-to-end test on a local throwaway page (no external sites, no cost).
- `templates/plan.example.json`, `templates/record_template.py` - starting points.
- `references/production-workflow.md` (plan schema, scene template, approval matrix),
  `references/recording-guidelines.md` (safe, reliable recording; pitfalls),
  `references/quality-checklist.md` (final review), `references/setup.md` (install, usage, examples).

Read the references when you reach the matching phase; do not preload them all.

## Phase 1 - Requirements (ask only what is missing)
Parse `$ARGUMENTS` and the conversation first. Gather, without re-asking anything already given:
target URL/app and start state; the exact workflow to show; purpose + audience; language, narration style
and voice; length, resolution, aspect ratio (default 1920x1080, 16:9, ~60-90 s); user-supplied assets
(sample input files, screenshots, brand colors/logo, reference videos); output location (default
`demoflow/<slug>/` in the current project); access method (existing session, env vars, test account).
Use AskUserQuestion only for decisions that change what gets built; otherwise pick a default, state it, go on.

## Phase 2 - Inspect the real workflow
1. `python ${CLAUDE_SKILL_DIR}/scripts/preflight.py` - report missing prerequisites with practical
   alternatives (see references/setup.md). Do not install anything without telling the user what and why.
2. Explore the live app yourself (Playwright script or an available browser tool): screenshots + visible text
   per state. Record the real labels, selectors, option availability, timings, and what each action does.
   Options can depend on earlier choices (a setting may hide or reveal other controls) - verify each one.
3. Identify every **consequential** action (submit, purchase, delete, publish, email, anything that spends credits
   or paid API calls, anything that writes real data). Note them for Phase 3 approval.
Desktop apps: use desktop automation only if no web version exists and tooling is available; otherwise ask the
user for a screen recording and build the video from that (assemble.py can cut any video given a timeline).

## Phase 3 - Plan (get approval)
Create `<workspace>/plan.json` (`preflight.py --init <workspace>` copies the template) with one scene per step:
id, title, purpose, actions, expected_state, narration, assets, and `speed_up_to` for long waits. Show the
user a readable scene table (number, title, purpose, actions, expected state, narration, approx. seconds,
captions/transition notes) plus an estimated total length. Narration: one short sentence or two per scene,
about 2.3 words/second; total must fit the requested length. **Ask for approval of the plan and explicitly
list consequential/paid actions** (what will be clicked, expected cost, number of live runs) before any real take.

## Phase 4 - Voice-over
`python ${CLAUDE_SKILL_DIR}/scripts/tts.py --plan <workspace>/plan.json`
Configure `tts.engine/voice/rate/pitch/pronunciations` from the user's wishes (`--list-voices --lang xx` for
edge-tts). Unchanged lines are reused from cache. Use `engine: silent` only for rehearsals. Check that
each scene's narration describes exactly what the scene shows; fix text, not the video, when they disagree.
If the narration is longer than the target length, shorten the script and re-run.

## Phase 5 - Record
Copy/edit `record.py` from the template using `recorder.Recorder` (set `DEMOFLOW_SCRIPTS` to the scripts dir).
1. Rehearse: `python record.py --dry` (consequential clicks skipped). Fix locators/timing until clean.
2. After approval, run the real take **once**. Never loop a paid/consequential action; on failure, read
   `work/fail_<scene>.png`, diagnose, and ask before re-spending.
3. Wait for real completion with `rec.wait_until(...)` on a verifiable condition. Capture a final-state
   screenshot (`rec.screenshot`). If the expected result does not appear, stop and report - do not fake it.
Auth: log in off-camera; keep passwords out of frames, logs, plans and Git (`work/` is git-ignored by `--init`).
Never bypass CAPTCHA, MFA, or other protections - ask the user to complete them or supply a saved session.

## Phase 6 - Assemble
`python ${CLAUDE_SKILL_DIR}/scripts/assemble.py --plan <workspace>/plan.json`
Outputs `<output_dir>/<basename>.mp4/.srt/.vtt/.script.md`. Background music only if the user asked
(`music` in plan.json; use licensed/user-provided files). Keep edits that aid comprehension; no gimmicks.

## Phase 7 - Validate (mandatory, then fix and re-validate)
`python ${CLAUDE_SKILL_DIR}/scripts/validate.py --plan <workspace>/plan.json`
Then **Read** `output/validation/contact_sheet.png` and the `frame_*.png` files and judge: correct scene vs
narration vs caption, readable text, banners/cursor visible, no stuck or blank frames, final state is the
real result. Work through `references/quality-checklist.md`. Fix what you find (re-record only if needed and
approved) and validate again. PASS from the script means "automated checks only".

## Phase 8 - Deliver
Report: video path; SRT/VTT paths; scene plan + narration (`.script.md`); supporting assets; metadata
(duration, resolution, fps, codecs, size); validation summary (what passed, what you looked at);
credits/paid calls actually used; leftover state created in the live app (test records, boards, etc.);
known limitations; what you did NOT do or could not verify (e.g. audio not listened to).
Offer next steps (other languages, aspect ratios, music) instead of doing unrequested work.

## Behavior rules
- Automate safe, reversible steps (inspection, planning, TTS, dry runs, rendering, validation). Ask first for
  consequential, paid, publishing, or out-of-scope actions, and for installing software.
- Do not overwrite user files or existing config; write into the workspace; scripts never delete outside `work/`.
- No secrets in frames, plans, logs, or commits. Do not commit unless asked.
- Report failures plainly with the evidence; never claim recording, voice-over, render, or validation succeeded
  unless the command exited 0 and you checked the output.

## Example invocations
- `/demoflow Show how to create an invoice in https://app.example.com, for new accounting staff, 75 s, British English, calm voice`
- `/demoflow Walk through the checkout of our staging shop (credentials in .env.staging), vertical 1080x1920 for social, no music`
- `/demoflow Explain the export feature of this desktop tool; here is my screen recording at ./raw/export.mp4 - add narration and captions`
