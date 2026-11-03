#!/usr/bin/env python3
"""Fast-cut vertical montage (1080x1920) from official campaign sources.

Each shot: center crop to 1080x1350 (4:5) with a slow punch-in zoom, a white
flash on entry, and its own original audio (no music / voiceover). Arabic text
is rendered with libass (correct Arabic shaping) with a pop-in animation, and a
progress bar runs along the bottom.

Usage: scripts/montage.py SPEC.json OUT.mp4

SPEC.json:
{
  "font": "fonts/Cairo-Black.ttf",
  "shots": [ {"src": "path.mp4", "start": 39.0, "dur": 1.8}, ... ],
  "texts": [ {"from": 0, "to": 2.5, "style": "Hook", "text": "..."}, ... ]
}
Styles: Top (small, white, persistent header), Hook (big yellow, center-top),
        Sub (white, under Hook), CTA (bottom).
"""
import json, os, shutil, subprocess, sys, tempfile

W, H, BOX_H = 1080, 1920, 1350
BOX_Y = (H - BOX_H) // 2 - 40
FPS = 30


def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass(spec, family, total):
    pop = r"{\fad(80,120)\fscx135\fscy135\t(0,180,\fscx100\fscy100)}"
    styles = {
        # name: size, primary(&HAABBGGRR), outline, align(8=top-center), marginV
        "Top":  (56, "&H00FFFFFF", 5, 8, 50),
        "Hook": (104, "&H0000D4FF", 8, 8, 125),
        "Sub":  (70, "&H00FFFFFF", 6, 8, 1615),
        "CTA":  (66, "&H00FFFFFF", 6, 8, 1730),
    }
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
           "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    for n, (sz, col, ol, al, mv) in styles.items():
        out.append(f"Style: {n},{family},{sz},{col},{col},&H00000000,&H80000000,-1,0,0,0,"
                   f"100,100,0,0,1,{ol},3,{al},40,40,{mv},-1")
    out += ["", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for t in spec["texts"]:
        end = min(t["to"], total)
        anim = "" if t["style"] == "Top" else pop
        out.append(f"Dialogue: 0,{ts(t['from'])},{ts(end)},{t['style']},,0,0,0,,{anim}{t['text']}")
    return "\n".join(out) + "\n"


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    font = spec.get("font", "fonts/Cairo-Black.ttf")
    family = subprocess.check_output(["fc-scan", "--format", "%{family[0]}", font], text=True)
    shots = spec["shots"]
    total = sum(s["dur"] for s in shots)

    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(f"{tmp}/fonts")
        shutil.copy(font, f"{tmp}/fonts/")
        open(f"{tmp}/text.ass", "w").write(ass(spec, family, total))

        # Pass 1: render each shot on its own (fast input seek, low memory).
        parts = []
        for i, s in enumerate(shots):
            a, d = s["start"], s["dur"]
            z = s.get("zoom", 0.12)  # punch-in amount over the shot
            if s.get("fit"):  # keep full 16:9 frame (logos / end cards), letterboxed
                fh = round(W * 9 / 16 / 2) * 2
                geo = (f"scale=w='trunc({W}*(1+{z}*t/{d})/2)*2':h=-2:eval=frame,"
                       f"crop={W}:{fh},pad={W}:{BOX_H}:0:(oh-ih)/2:black,")
            else:             # fill 4:5 box, center crop
                geo = (f"scale=w='trunc({BOX_H}*16/9*(1+{z}*t/{d})/2)*2':"
                       f"h='trunc({BOX_H}*(1+{z}*t/{d})/2)*2':eval=frame,"
                       f"crop={W}:{BOX_H},")
            vf = (f"fps={FPS},{geo}setsar=1,format=yuv420p,"
                  f"fade=t=in:st=0:d=0.15:color=white")
            af = (f"aformat=sample_rates=48000:channel_layouts=stereo,"
                  f"afade=t=in:d=0.03,afade=t=out:st={d - 0.05}:d=0.05")
            part = f"{tmp}/shot{i:02d}.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(d),
                            "-i", s["src"], "-vf", vf, "-af", af,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
                            "-c:a", "pcm_s16le", part], check=True)
            parts.append(part)
            print(f"  shot {i + 1}/{len(shots)}", flush=True)

        # Pass 2: join shots, add background, progress bar, Arabic text, loudness.
        args = ["ffmpeg", "-v", "error", "-y"]
        for p in parts:
            args += ["-i", p]
        fc = ["".join(f"[{i}:v][{i}:a]" for i in range(len(parts)))
              + f"concat=n={len(parts)}:v=1:a=1[mv][ma]"]
        fc.append(f"color=c=0x0B0B0B:s={W}x{H}:r={FPS}:d={total}[bg]")
        fc.append(f"color=c=0xFFD400:s={W}x14:r={FPS}:d={total}[bar]")
        fc.append(f"[bg][mv]overlay=0:{BOX_Y}:shortest=1[c1]")
        fc.append(f"[c1][bar]overlay=x='-W+W*t/{total}':y={H - 14}:shortest=1[c2]")
        fc.append(f"[c2]subtitles={tmp}/text.ass:fontsdir={tmp}/fonts[vo]")
        fc.append(f"[ma]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={total - 1}:d=1[ao]")

        args += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
        subprocess.run(args, check=True)
        print(f"wrote {out} ({total:.1f}s)")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
