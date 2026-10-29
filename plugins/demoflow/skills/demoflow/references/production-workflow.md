# Production workflow reference

## Workspace layout (default `demoflow/<slug>/` inside the user's project; configurable)
```
<workspace>/
  plan.json          scene plan + TTS/video/caption settings   (commit-safe, no secrets)
  record.py          per-video recording script                (commit-safe, no secrets)
  assets/            user-provided inputs (sample files, logos, music)
  work/              audio cache, raw recording, segments, tts.json, timeline.json   (git-ignored)
  output/            <basename>.mp4 / .srt / .vtt / .script.md / validation/
```
`preflight.py --init <workspace>` creates plan.json, record.py and a .gitignore entry list; existing files are kept.

## plan.json schema (all keys optional except `scenes`)
| key | meaning | default |
|---|---|---|
| title, language, basename | metadata, output file stem | "Demo video", en-US, demo |
| output_dir, work_dir | relative to plan.json | output, work |
| tts.engine | `edge-tts` / `command` / `silent` | edge-tts |
| tts.voice/rate/pitch/volume | engine voice settings (edge-tts format: `+10%`, `-2Hz`) | en-US-AriaNeural, +0% |
| tts.pronunciations | `{"Brand": "Re-spelling"}` applied to spoken text only; captions keep the original | {} |
| tts.command / ext | for `command`: template with `{text_file}` and `{out}` | - |
| video.width/height/fps/crf/preset | output (also the recording size) | 1920x1080, 30, 18, medium |
| captions.burn_in/formats/font/font_file/size/max_words | caption look; formats `srt`,`vtt` | true, both, auto font, 46, 8 |
| timing.lead/tail/fade_in/fade_out | narration lead-in, hold after speech, fades (s) | 0.15, 0.5, 0.6, 0.9 |
| music | `{"file": "...", "volume": 0.08}` - only if requested | null |
| scenes[] | see below | required |

Scene: `id` (unique), `title` (banner), `narration`, plus planning fields `purpose`, `actions`,
`expected_state`, `assets`; optional `label` (banner text instead of "STEP n/N", e.g. INTRO/DONE),
`numbered` (false to exclude from numbering), `banner` (false to hide), `speed_up_to` (seconds: if the real
scene is longer it is sped up to this length - for waits), `optional` (assemble may skip if not recorded).

## Scene plan table to show the user
| # | Title | Purpose | On-screen actions | Expected state | Narration | Assets | ~s | Caption/transition |
Typical sequence: intro (what you will learn) -> prerequisites (only if needed) -> numbered steps ->
(wait, sped up, honestly labelled) -> final result -> short conclusion. 6-12 scenes for a 60-90 s video.

## Timing guidance
Speech about 2.3 words/s (~150 wpm). A scene lasts max(actions, narration + lead + tail). Keep actions
within the narration so there is no dead air; if an action is slow (typing, scrolling) shorten it or lengthen
the narration. Budget live waits: speed them up (`speed_up_to` 6-8 s) and say so in the narration.

## Approval matrix
| Action | Automatic? |
|---|---|
| preflight, inspect (read-only), draft plan, TTS to a local cache, dry-run recording, render, validate | yes |
| installing packages/browsers | ask (say what/why) |
| anything that submits/creates/deletes/spends credits/emails/publishes in the live app | ask, with cost and run count |
| re-running a paid action after a failed take | ask again |
| writing outside the workspace, committing, publishing the video | ask |

## Multiple takes and re-use
- Narration unchanged -> audio is reused from `work/audio` (hash of text+voice+settings).
- Only recording changed -> rerun `record.py` then `assemble.py`. Only wording changed -> `tts.py`, then
  re-record only if scene timing/content changed; else assemble fails loudly if timeline and audio disagree.
- `timeline.json` is only written by a successful recording. Never assemble a stale one.
