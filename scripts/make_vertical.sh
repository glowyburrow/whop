#!/usr/bin/env bash
# Build a 1080x1920 campaign clip (Template A) from one official source video.
# Uses only the source's own audio (no music / voiceover), Arabic on-screen text.
#
# Usage:
#   scripts/make_vertical.sh SOURCE OUT SEGMENTS HOOK1 HOOK2 [CTA] [FONT]
#     SEGMENTS  comma-separated start-end seconds, e.g. "72-99,114-118"
#     HOOK1     white top line (Arabic)
#     HOOK2     yellow top line (Arabic)
#     CTA       bottom line shown in the last 10s (Arabic, optional)
#     FONT      TTF with full Arabic coverage (default: fonts/Cairo-Black.ttf)
set -euo pipefail

SRC=$1 OUT=$2 SEGS=$3 HOOK1=$4 HOOK2=$5 CTA=${6:-} FONT=${7:-fonts/Cairo-Black.ttf}
[[ -f $FONT ]] || { echo "font not found: $FONT" >&2; exit 1; }

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# Trim + concat each segment (video and audio).
fc="" ; cat_in="" ; n=0 ; total=0
IFS=, read -ra parts <<< "$SEGS"
for p in "${parts[@]}"; do
  s=${p%-*} e=${p#*-}
  fc+="[0:v]trim=$s:$e,setpts=PTS-STARTPTS[v$n];[0:a]atrim=$s:$e,asetpts=PTS-STARTPTS[a$n];"
  cat_in+="[v$n][a$n]"
  total=$(awk -v t="$total" -v s="$s" -v e="$e" 'BEGIN{print t+e-s}')
  n=$((n+1))
done
fade=$(awk -v t="$total" 'BEGIN{print (t>1.5)?t-1.5:0}')
cta_from=$(awk -v t="$total" 'BEGIN{print (t>10)?t-10:0}')

# Arabic text via libass (HarfBuzz shaping; drawtext in ffmpeg 6 breaks Arabic letters).
fam=$(fc-scan --format '%{family[0]}' "$FONT")
mkdir -p "$tmp/fonts"; cp "$FONT" "$tmp/fonts/"
ts() { awk -v t="$1" 'BEGIN{h=int(t/3600);m=int(t%3600/60);s=t-h*3600-m*60;printf "%d:%02d:%05.2f",h,m,s}'; }
{
  echo "[Script Info]"; echo "ScriptType: v4.00+"; echo "PlayResX: 1080"; echo "PlayResY: 1920"; echo
  echo "[V4+ Styles]"
  echo "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
  echo "Style: H1,$fam,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,8,40,40,330,1"
  echo "Style: H2,$fam,92,&H0000D4FF,&H0000D4FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,8,40,40,450,1"
  echo "Style: CTA,$fam,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,8,40,40,1450,1"
  echo; echo "[Events]"
  echo "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
  echo "Dialogue: 0,0:00:00.00,$(ts "$total"),H1,,0,0,0,,$HOOK1"
  echo "Dialogue: 0,0:00:00.00,$(ts "$total"),H2,,0,0,0,,$HOOK2"
  [[ -z $CTA ]] || echo "Dialogue: 0,$(ts "$cta_from"),$(ts "$total"),CTA,,0,0,0,,$CTA"
} > "$tmp/text.ass"
fc+="${cat_in}concat=n=$n:v=1:a=1[v][au];"
fc+="[v]fps=30,split[v1][v2];"
fc+="[v1]scale=-2:1920,crop=1080:1920,boxblur=30:2,eq=brightness=-0.15[bg];"
fc+="[v2]scale=1080:-2[fg];"
fc+="[bg][fg]overlay=0:(H-h)/2,subtitles=$tmp/text.ass:fontsdir=$tmp/fonts[vo];"
fc+="[au]afade=t=out:st=$fade:d=1.5[ao]"

ffmpeg -v error -y -i "$SRC" -filter_complex "$fc" -map "[vo]" -map "[ao]" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -movflags +faststart "$OUT"
echo "wrote $OUT (${total}s)"
