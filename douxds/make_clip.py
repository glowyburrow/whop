#!/usr/bin/env python3
"""Douxds x MANE clip builder: 1080x1920 TikTok/Reels video from campaign assets.

Usage: douxds/make_clip.py SPEC.json OUT.mp4

SPEC.json
{
  "shots": [
    {"src": "ugc/clip.mp4", "start": 3.0, "dur": 2.0, "zoom": 0.08, "punch": 0.0, "y": 0.5},
    {"img": "product/flex_reveal.jpg", "dur": 3.0, "fit": "blur"}   # product slide
  ],
  "texts": [
    {"from": 0, "to": 2.5, "style": "Hook", "text": "line one\\Nline two"}
  ],
  "audio": "mute"            # "mute" (add trending sound in-app) | "source"
}

Text styles look native to TikTok: white rounded-ish box + black text (Hook / Step),
plain white with outline (Sub), and the end-card brand line (Brand).
Hook/Step boxes sit at the top band so they also cover captions burned into the UGC.
Paths in "src"/"img" are relative to sources_douxds/.
"""
import json, os, shutil, subprocess, sys, tempfile

W, H, FPS = 1080, 1920, 30
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sources_douxds")
FONT = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

# name: size, primary, outline colour, border style (3 = opaque box), outline, align, marginV
STYLES = {
    "Hook":  (88, "&H00000000", "&H00FFFFFF", 3, 14, 8, 300),
    "Step":  (78, "&H00000000", "&H00FFFFFF", 3, 14, 8, 300),
    "Sub":   (62, "&H00FFFFFF", "&H00000000", 1, 5, 2, 420),
    "Brand": (84, "&H00FFFFFF", "&H00000000", 1, 6, 8, 260),
    "Small": (54, "&H00FFFFFF", "&H00000000", 1, 4, 2, 300),
}


def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass(texts, total):
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
           "WrapStyle: 0", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
           "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
    for n, (sz, pc, oc, bs, ol, al, mv) in STYLES.items():
        out.append(f"Style: {n},Inter,{sz},{pc},{pc},{oc},&H00000000,-1,0,0,0,"
                   f"100,100,0,0,{bs},{ol},0,{al},90,90,{mv},1")
    out += ["", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    pop = r"{\fad(60,80)\fscx118\fscy118\t(0,140,\fscx100\fscy100)}"
    for t in texts:
        end = min(t["to"], total)
        anim = "" if t.get("static") else pop
        out.append(f"Dialogue: 0,{ts(t['from'])},{ts(end)},{t['style']},,0,0,0,,{anim}{t['text']}")
    return "\n".join(out) + "\n"


def render_shot(s, part):
    d = s["dur"]
    z = s.get("zoom", 0.06)
    pu = s.get("punch", 0.0)
    k = f"(1+{z}*t/{d}+{pu}*max(0,1-t/0.2))"
    if "img" in s:
        src = os.path.join(ROOT, s["img"])
        # product slide: sharp image fitted to width over a blurred, darkened fill
        vf = (f"scale={W*2}:-2,split[b][f];"
              f"[b]scale=-2:{H},crop={W}:{H},boxblur=30:2,eq=brightness=-0.25[bb];"
              f"[f]scale=w='trunc({W}*{s.get('scale', 1.45)}*{k}/2)*2':h=-2:eval=frame,crop='min(iw,{W})':'min(ih,{H})'[ff];"
              f"[bb][ff]overlay=(W-w)/2:(H-h)/2-{s.get('lift', 80)},fps={FPS},setsar=1,format=yuv420p,"
              f"fade=t=in:st=0:d=0.12:color=white")
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(d),
               "-i", src, "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
               "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
    else:
        src = os.path.join(ROOT, s["src"])
        y = s.get("y", 0.5)
        sp = s.get("speed", 1.0)
        # "cover": [y0, y1] band (output px) blurred to hide captions burned into the UGC
        cv = s.get("cover", [170, 520])
        band = ""
        if cv:
            y0, y1 = cv
            band = (f"split[m][c];[c]crop={W}:{y1 - y0}:0:{y0},boxblur=28:3[cb];"
                    f"[m][cb]overlay=0:{y0},")
        vf = (f"setpts=(PTS-STARTPTS)/{sp},fps={FPS},"
              f"scale=w='trunc({W}*{k}/2)*2':h='trunc({H}*{k}/2)*2':eval=frame,"
              f"crop={W}:{H}:(iw-ow)/2:(ih-oh)*{y},{band}setsar=1,format=yuv420p,"
              + ("eq=saturation=1.08:contrast=1.04," if s.get("grade", True) else "")
              + "fade=t=in:st=0:d=0.08:color=white")
        af = "aformat=sample_rates=48000:channel_layouts=stereo" + (f",atempo={sp}" if sp != 1 else "")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(s["start"]), "-t", str(round(d * sp, 3)),
               "-i", src, "-vf", vf, "-af", af]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-c:a", "pcm_s16le",
            "-t", str(d), part]
    subprocess.run(cmd, check=True)


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    shots = spec["shots"]
    total = round(sum(s["dur"] for s in shots), 3)
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(f"{tmp}/fonts")
        shutil.copy(FONT, f"{tmp}/fonts/")
        open(f"{tmp}/text.ass", "w").write(ass(spec["texts"], total))
        parts = []
        for i, s in enumerate(shots):
            p = f"{tmp}/shot{i:02d}.mkv"
            render_shot(s, p)
            parts.append(p)
        args = ["ffmpeg", "-v", "error", "-y"]
        for p in parts:
            args += ["-i", p]
        n = len(parts)
        fc = ["".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[mv][ma]",
              f"[mv]subtitles={tmp}/text.ass:fontsdir={tmp}/fonts[vo]"]
        if spec.get("audio", "mute") == "mute":
            fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total}[ao]")
            fc.append("[ma]anullsink")
        else:
            fc.append(f"[ma]loudnorm=I=-14:TP=-1.5,afade=t=out:st={total - 0.6}:d=0.6[ao]")
        args += ["-filter_complex", ";".join(fc), "-map", "[vo]", "-map", "[ao]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                 "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                 "-movflags", "+faststart", "-t", str(total), out]
        subprocess.run(args, check=True)
        print(f"wrote {out} ({total:.1f}s)")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
