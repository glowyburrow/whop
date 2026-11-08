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

W, H, FPS = 1080, 1920, 30
# layout "box": 4:5 picture between title bars; "full": full-screen 9:16 for phones
LAYOUTS = {
    "box":  {"box_h": 1350, "box_y": (1920 - 1350) // 2 - 40,
             "styles": {"Top": (56, 5, 50), "Hook": (104, 8, 125), "Brand": (40, 4, 112),
                        "Date": (36, 4, 1830),
                        "Sub": (70, 6, 1615), "CTA": (66, 6, 1730)}},
    "full": {"box_h": 1920, "box_y": 0,
             "styles": {"Top": (88, 6, 150), "Brand": (44, 4, 250), "Date": (40, 4, 308),
                        "Hook": (100, 8, 380),
                        "Sub": (72, 6, 1330), "CTA": (66, 6, 1450)}},
}
COLORS = {"Top": "&H00FFFFFF", "Brand": "&H0000D4FF", "Date": "&H00E6E6E6", "Hook": "&H0000D4FF",
          "Sub": "&H00FFFFFF", "CTA": "&H00FFFFFF"}


def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass(spec, family, total, layout):
    pop = r"{\fad(80,120)\fscx135\fscy135\t(0,180,\fscx100\fscy100)}"
    # name: size, primary(&HAABBGGRR), outline, align(8=top-center), marginV
    styles = {n: (sz, COLORS[n], ol, 8, mv) for n, (sz, ol, mv) in layout["styles"].items()}
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
        anim = "" if t["style"] in ("Top", "Brand", "Date") else pop
        out.append(f"Dialogue: 0,{ts(t['from'])},{ts(end)},{t['style']},,0,0,0,,{anim}{t['text']}")
    return "\n".join(out) + "\n"


def main():
    global FPS
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    FPS = spec.get("fps", 30)
    hq = spec.get("hq", False)  # higher-quality encode + colour grade + sharpen
    font = spec.get("font", "fonts/Cairo-Black.ttf")
    family = subprocess.check_output(["fc-scan", "--format", "%{family[0]}", font], text=True)
    shots = spec["shots"]
    total = sum(s["dur"] for s in shots)
    layout = LAYOUTS[spec.get("layout", "box")]
    BOX_H, BOX_Y = layout["box_h"], layout["box_y"]
    full = BOX_H == H

    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(f"{tmp}/fonts")
        shutil.copy(font, f"{tmp}/fonts/")
        open(f"{tmp}/text.ass", "w").write(ass(spec, family, total, layout))

        # Pass 1: render each shot on its own (fast input seek, low memory).
        parts = []
        fx = spec.get("fx", {})  # defaults for every shot: punch (zoom-in hit), glitch (RGB split on cut)
        for i, s in enumerate(shots):
            a, d = s["start"], s["dur"]
            pu = s.get("punch", fx.get("punch", 0))
            gl = s.get("glitch", fx.get("glitch", False)) and not s.get("fit")
            z = s.get("zoom", 0.12)  # punch-in amount over the shot
            x = s.get("x", 0.5)  # horizontal crop position, 0=left .. 1=right
            if s.get("fit") and full:  # whole 16:9 frame over a blurred fill
                fh = round(W * 9 / 16 / 2) * 2
                geo = (f"split[b][f];[b]scale=-2:{BOX_H},crop={W}:{BOX_H},boxblur=40:2,"
                       f"eq=brightness=-0.2[bb];"
                       f"[f]scale=w='trunc({W}*(1+{z}*t/{d})/2)*2':h=-2:eval=frame:flags=lanczos,crop={W}:{fh}[ff];"
                       f"[bb][ff]overlay=0:(H-h)/2,")
            elif s.get("fit"):  # keep full 16:9 frame (logos / end cards), letterboxed
                fh = round(W * 9 / 16 / 2) * 2
                geo = (f"scale=w='trunc({W}*(1+{z}*t/{d})/2)*2':h=-2:eval=frame:flags=lanczos,"
                       f"crop={W}:{fh},pad={W}:{BOX_H}:0:(oh-ih)/2:black,")
            else:             # fill the box, crop at x (optional camera shake)
                sh = s.get("shake", 0)  # shake amplitude in px
                base = 1 + (0.06 if sh else 0)
                k = f"({base}+{z}*t/{d}+{pu}*max(0,1-t/0.22))"
                geo = (f"scale=w='trunc({BOX_H}*16/9*{k}/2)*2':"
                       f"h='trunc({BOX_H}*{k}/2)*2':eval=frame:flags=lanczos,"
                       f"crop={W}:{BOX_H}:x='(iw-ow)*{x}+{sh}*sin(t*53)':"
                       f"y='(ih-oh)/2+{sh}*cos(t*47)',")
            sp = s.get("speed", 1.0)  # <1 slow motion, >1 fast
            glitch = "rgbashift=rh=-26:bh=26:gv=8:enable='lt(t,0.12)'," if gl else ""
            vf = (f"setpts=(PTS-STARTPTS)/{sp},fps={FPS},{geo}{glitch}setsar=1,format=yuv420p,"
                  f"fade=t=in:st=0:d=0.15:color=white")
            af = (f"aformat=sample_rates=48000:channel_layouts=stereo,"
                  + (f"atempo={sp}," if sp != 1.0 else "")
                  + f"afade=t=in:d=0.03,afade=t=out:st={d - 0.05}:d=0.05")
            part = f"{tmp}/shot{i:02d}.mkv"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(round(d * sp, 3)),
                            "-i", s["src"], "-vf", vf, "-af", af,
                            "-c:v", "libx264", "-preset", "fast" if hq else "veryfast", "-crf", "10" if hq else "14",
                            "-c:a", "pcm_s16le", "-t", str(d), part], check=True)
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
        shade = ""
        if full:  # darken behind the text so it reads on any footage
            shade = ("drawbox=y=0:w=iw:h=420:color=black@0.40:t=fill,"
                     "drawbox=y=420:w=iw:h=200:color=black@0.18:t=fill,"
                     "drawbox=y=1280:w=iw:h=300:color=black@0.25:t=fill,")
        fc.append(f"[c1]{shade}null[c1s]")
        fc.append(f"[c1s][bar]overlay=x='-W+W*t/{total}':y={H - 14}:shortest=1[c2]")
        grade = "eq=contrast=1.07:saturation=1.18:gamma=0.98,unsharp=5:5:0.55:5:5:0," if hq else ""
        fc.append(f"[c2]{grade}subtitles={tmp}/text.ass:fontsdir={tmp}/fonts[vo]")
        fc.append(f"[ma]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={total - 1}:d=1[ao]")

        args += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]",
                 "-c:v", "libx264", "-preset", "slow" if hq else "medium", "-crf", "16" if hq else "19",
                 "-profile:v", "high", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
        subprocess.run(args, check=True)
        print(f"wrote {out} ({total:.1f}s)")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
