# Recording guidelines

## Reliability
- Prefer role/label/text locators (`get_by_role`, `get_by_label`) over CSS classes. Scope ambiguous ones to a
  container (`page.get_by_label("Garment category").get_by_role(...)`); Playwright's strict mode errors when
  two elements match - read the error, don't add `.first` blindly (it may pick a hidden duplicate).
- Not every control is a `<button>`: pills may be `label`+`input[type=radio]`. Inspect the DOM before guessing.
- Wait on conditions, not sleeps: `rec.wait_until(lambda: ..., timeout=..)` for results; `expect_file_chooser`
  or `set_input_files` for uploads. A timeout is a finding to report, never something to paper over.
- First-visit popups (tours, cookie banners): dismiss them off-camera or with `dispatch_event("click")` when the
  intro card covers them (the card intercepts real mouse clicks).
- Options can depend on earlier choices (a model/plan/type may hide controls). Verify the UI after each choice.
- Sticky headers/overlays can cover targets; `rec.reveal()` scrolls to center. Re-check by screenshot on failure
  (`work/fail_<scene>.png` is written automatically).

## Making it watchable
- Move the cursor to the target before clicking (`rec.click` does); hold ~0.25 s before the click.
- One idea per scene, 4-9 s. Let results sit on screen for the length of the narration.
- 1920x1080 viewport gives readable text; for vertical output set video.width/height (e.g. 1080x1920) and use
  a mobile viewport/context option.
- Show intermediate states that prove progress (progress panel, filled form) and the verified end state.
- Sped-up waits must be labelled in narration ("we have sped up the wait"). Never cut a failure out of a wait
  and present it as success.

## Safety
- **Secrets**: never type, print, log, screenshot, or commit passwords/API keys/tokens. Authenticate before
  recording (saved `storage_state` in `work/`, which is git-ignored) or via env vars. Do not read `.env` files
  aloud in plans or narration. If credentials are only in a project's server `.env`, load them at runtime in a
  login script and ask the user which account/email is meant when several exist.
- **Private data**: blur/avoid customer data, emails, balances, API keys visible in the UI. Prefer a test or
  demo account; tell the user what is visible in frames.
- **Protections**: never bypass CAPTCHA, MFA, rate limits, paywalls, or terms of service. If one appears, stop
  and ask the user to complete it or provide a session. Only automate sites the user is entitled to use.
- **Paid / destructive actions**: use `consequential=True` on the click, rehearse with `--dry`, run the real take
  once after approval, never retry blindly, and report the credits/cost actually consumed.
- **Duplicate submissions**: after any submit, wait for the app's own completion signal; do not click again.
- **Live-state hygiene**: list what the take created (records, drafts, uploaded files) in the final report; do
  not delete user data without being asked.

## Desktop software
Only when no web equivalent exists. Check what is available (e.g. OS-level automation, an Electron/CDP
connection, or the user's own screen recording). If automation is unavailable, ask the user for a recording
and produce the timeline manually (`timeline.json` with `{"timeline":[{"id","t0","t1"}],"video":"path","sync_t":null}`;
t0/t1 are seconds in that video) so `assemble.py` can still add narration, captions, and speed-ups.

## Pitfalls learned (FFmpeg 4.2-era builds, Playwright WebM)
- Playwright's WebM is variable-frame-rate; the `trim` filter yields wrong timestamps. Cut with input seeking
  (`-ss/-t` before `-i`) - assemble.py does this.
- In `setpts`, put `fps=` BEFORE the speed change and multiply (`0.16*(PTS-STARTPTS)`); dividing or putting `fps`
  after can silently leave the length unchanged. Verify durations after any speed-up change.
- `adelay` has no `all=1` on old builds (mono audio: `adelay=150`); `amix` has no `normalize` (compensate with `volume`).
- The `subtitles` filter breaks on Windows drive-letter paths: run ffmpeg with `cwd` = work dir and relative file
  names (assemble.py does this). Without libass, only sidecar SRT/VTT are possible.
- Video time != script clock: the recorder flashes a magenta frame and assemble.py finds it to measure the
  offset. Never skip `rec.open()` (it emits the flash) in new recording scripts.
