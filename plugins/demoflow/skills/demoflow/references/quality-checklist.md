# Final quality checklist

Run `validate.py`, then LOOK at `output/validation/contact_sheet.png` and every `frame_<scene>.png`. Tick each
item with evidence; fix and re-validate anything that fails.

## Truthfulness
- [ ] Every action/result shown happened in the real app during this take (final-state screenshot exists).
- [ ] Narration claims only what the screen shows (no invented features, prices, speed claims).
- [ ] Sped-up or trimmed parts are labelled; no failure is presented as success.
- [ ] Credits/paid calls used and leftover live-app state are listed in the report.

## Sync and pacing
- [ ] Each scene's banner/step label matches the on-screen state at its mid-frame.
- [ ] Captions match the narration words and appear with the speech (spot-check start, middle, end).
- [ ] No dead air over `--max-silence` unless intentional; no scene shorter than its narration.
- [ ] Total length within the requested range.

## Visuals
- [ ] Text readable at 100% (captions not covering the thing being explained; font size adequate).
- [ ] Cursor visible, clicks have ripples, cursor motion is smooth not teleporting.
- [ ] Intro/outro/transitions are simple and short; fades at start/end; no black or frozen frames mid-video.
- [ ] Consistent resolution/aspect/frame rate; no letterbox artefacts unless intended.
- [ ] No passwords, tokens, API keys, or private customer data visible anywhere.

## Audio
- [ ] Audio stream present; mean level about -16 to -26 dB, no clipping (validate prints levels).
- [ ] Pronunciations of product/brand/technical terms fixed via `tts.pronunciations` where wrong.
- [ ] If you could not listen (headless), say so in the report.

## Files and hygiene
- [ ] mp4 plays (validate decodes it end to end), SRT/VTT exist and are within the video length.
- [ ] `work/` (auth state, raw recordings) is git-ignored; no secrets in plan.json/record.py/logs.
- [ ] Nothing outside the workspace was modified; no commits unless asked.
- [ ] Known limitations and not-done items are stated in the delivery message.
