#!/usr/bin/env bash
# Required No Scope podcast format: podcast on TOP, streamer clip on BOTTOM,
# audio from the podcast ONLY. Output 1080x1920.
#
# Usage:
#   scripts/split_podcast.sh PODCAST P_START STREAMER S_START DURATION OUT
#     P_START / S_START  start time in seconds in each file
#     DURATION           clip length in seconds (>= 10)
set -euo pipefail

POD=$1 PS=$2 STR=$3 SS=$4 DUR=$5 OUT=$6
awk -v d="$DUR" 'BEGIN{exit !(d>=10)}' || { echo "duration must be >= 10s" >&2; exit 1; }

ffmpeg -v error -y \
  -ss "$PS" -t "$DUR" -i "$POD" \
  -ss "$SS" -t "$DUR" -i "$STR" \
  -filter_complex "
    [0:v]fps=30,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[top];
    [1:v]fps=30,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[bot];
    [top][bot]vstack=inputs=2[vo]" \
  -map "[vo]" -map 0:a:0 \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest -movflags +faststart "$OUT"
echo "wrote $OUT"
