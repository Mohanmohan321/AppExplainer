"""Validate the exported video and produce evidence for a visual review.

  python validate.py --plan PLAN [--video FILE] [--max-silence 6]

Checks (HARD = exit code 1): file exists and decodes; has video + audio; resolution/fps match the plan;
duration matches the assembled timeline; audio not silent/clipped; captions present, ordered,
inside the video. Warnings: long silences, black frames, frozen stretches, no burned-in captions.
Evidence written to <output_dir>/validation/: frame_<scene>.png (mid-scene), contact_sheet.png,
validation.json. YOU must still look at the frames - this script cannot judge clarity or correctness.
"""
import argparse, json, re, subprocess
from pathlib import Path
from _common import Workspace, find_tool, run


def probe(ffmpeg, ffprobe, f):
    if ffprobe:
        r = run([ffprobe, "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                 "-of", "json", str(f)])
        j = json.loads(r.stdout or "{}")
        v = next((s for s in j.get("streams", []) if s["codec_type"] == "video"), None)
        a = next((s for s in j.get("streams", []) if s["codec_type"] == "audio"), None)
        n, d = (v["r_frame_rate"].split("/") + ["1"])[:2] if v else ("0", "1")
        return {"duration": float(j["format"]["duration"]), "size": int(j["format"]["size"]),
                "video": v and {"codec": v["codec_name"], "width": v["width"], "height": v["height"], "fps": float(n) / float(d or 1)},
                "audio": a and {"codec": a["codec_name"], "rate": a.get("sample_rate"), "channels": a.get("channels")}}
    err = run([ffmpeg, "-hide_banner", "-i", str(f)]).stderr
    dm = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
    vm = re.search(r"Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) fps", err, re.S)
    am = re.search(r"Audio: (\w+).*?, (\d+) Hz, (\w+)", err)
    return {"duration": int(dm[1]) * 3600 + int(dm[2]) * 60 + float(dm[3]) if dm else 0, "size": Path(f).stat().st_size,
            "video": vm and {"codec": vm[1], "width": int(vm[2]), "height": int(vm[3]), "fps": float(vm[4])},
            "audio": am and {"codec": am[1], "rate": am[2], "channels": am[3]}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--plan", required=True); ap.add_argument("--video")
    ap.add_argument("--max-silence", type=float, default=6.0)
    a = ap.parse_args(); ws = Workspace(a.plan)
    ff, fp = find_tool("ffmpeg"), find_tool("ffprobe")
    rep_path = ws.work / "assemble_report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.exists() else None
    video = Path(a.video) if a.video else ws.out / (ws.plan["basename"] + ".mp4")
    hard, warn, info = [], [], {}
    if not video.exists():
        print(f"HARD FAIL: {video} does not exist"); raise SystemExit(1)
    m = probe(ff, fp, video); info["metadata"] = m
    if run([ff, "-v", "error", "-i", str(video), "-f", "null", "-"]).stderr.strip():
        hard.append("decode errors reported by ffmpeg")
    cfg = ws.plan["video"]
    if not m["video"]: hard.append("no video stream")
    else:
        if (m["video"]["width"], m["video"]["height"]) != (cfg["width"], cfg["height"]):
            hard.append(f"resolution {m['video']['width']}x{m['video']['height']} != plan {cfg['width']}x{cfg['height']}")
        if abs(m["video"]["fps"] - cfg["fps"]) > 0.5: hard.append(f"fps {m['video']['fps']:.2f} != plan {cfg['fps']}")
    if not m["audio"]: hard.append("no audio stream")
    if rep and abs(m["duration"] - rep["total"]) > 1.0:
        hard.append(f"duration {m['duration']:.1f}s differs from assembled timeline {rep['total']:.1f}s (sync/speed bug?)")

    if m["audio"]:
        s = run([ff, "-hide_banner", "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"]).stderr
        mean = re.search(r"mean_volume: (-?[\d.]+) dB", s); mx = re.search(r"max_volume: (-?[\d.]+) dB", s)
        if mean and mx:
            info["audio_levels_db"] = {"mean": float(mean[1]), "max": float(mx[1])}
            if float(mean[1]) < -45:
                if ws.plan["tts"]["engine"] == "silent":
                    warn.append("audio is silent because tts.engine='silent' (rehearsal/test only - NOT a deliverable)")
                else:
                    hard.append("audio is (near) silent")
            if float(mx[1]) > -0.1: hard.append("audio clips (max ~0 dB)")
        sil = run([ff, "-hide_banner", "-i", str(video), "-af", f"silencedetect=noise=-40dB:d={a.max_silence}", "-vn", "-f", "null", "-"]).stderr
        gaps = [(float(x), float(y)) for x, y in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", sil)]
        info["long_silences"] = gaps
        for g0, g1 in gaps: warn.append(f"silence {g0:.1f}-{g1:.1f}s ({g1-g0:.1f}s) - dead air; shorten the action or add narration")
    bl = run([ff, "-hide_banner", "-i", str(video), "-vf", "blackdetect=d=0.8:pix_th=0.05", "-an", "-f", "null", "-"]).stderr
    for s0, s1 in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bl):
        if float(s0) > 0.1 and float(s1) < m["duration"] - 1.2: warn.append(f"black frames {s0}-{s1}s mid-video")
    fr = run([ff, "-hide_banner", "-i", str(video), "-vf", "freezedetect=n=-60dB:d=8", "-an", "-f", "null", "-"]).stderr
    for s0 in re.findall(r"freeze_start: ([\d.]+)", fr): warn.append(f"video frozen for 8s+ starting {float(s0):.1f}s (intentional hold?)")

    if rep:
        cues = rep["cues"]
        if not cues: warn.append("no caption cues (scenes without narration?)")
        if any(c["end"] <= c["start"] for c in cues) or any(cues[i]["end"] > cues[i + 1]["start"] + 0.01 for i in range(len(cues) - 1)):
            hard.append("caption cues overlap or have non-positive length")
        if cues and cues[-1]["end"] > m["duration"] + 0.1: hard.append("last caption ends after the video")
        if not rep["burned_captions"]: warn.append("captions are not burned in (sidecar SRT/VTT only)")
        info["caption_cues"] = len(cues)

    ev = ws.out / "validation"; ev.mkdir(parents=True, exist_ok=True); frames = []
    if rep:
        for q in rep["scenes"]:
            t = q["out_start"] + q["out_len"] * 0.6
            f = ev / f"frame_{q['id']}.png"
            run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=960:-2", str(f)])
            if f.exists(): frames.append(str(f))
    cols = 3; rows = max(1, -(-max(1, len(frames)) // cols)); step = max(1.0, m["duration"] / (cols * rows))
    run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf", f"fps=1/{step:.2f},scale=640:-2,tile={cols}x{rows}:padding=4:color=black",
         "-frames:v", "1", str(ev / "contact_sheet.png")])
    info.update(frames=frames, contact_sheet=str(ev / "contact_sheet.png"), hard_failures=hard, warnings=warn)
    (ev / "validation.json").write_text(json.dumps(info, indent=1), encoding="utf-8")

    mv, ma = m["video"], m["audio"]
    print(f"file      {video}  ({m['size']/1e6:.1f} MB)\nduration  {m['duration']:.1f}s")
    if mv: print(f"video     {mv['codec']} {mv['width']}x{mv['height']} @ {mv['fps']:.2f} fps")
    if ma: print(f"audio     {ma['codec']} {ma['rate']} Hz {ma['channels']}")
    print("levels   ", info.get("audio_levels_db"), "\ncues     ", info.get("caption_cues"))
    for w in warn: print("WARN     ", w)
    for h in hard: print("HARD FAIL", h)
    print("evidence ", ev, "- open frame_*.png and contact_sheet.png and LOOK at them before reporting done")
    print("RESULT   ", "FAIL" if hard else "PASS (automated checks only)")
    raise SystemExit(1 if hard else 0)


if __name__ == "__main__":
    main()
