#!/usr/bin/env bash
# Minimal FFmpeg for SkyrimVoiceRefs, compiled from FFmpeg's official source: read xWMA, decode WMA v2, resample,
# write 16-bit WAV - nothing else. LGPL 2.1 or later (no GPL, nonfree or version-3 parts).
#
# usage: tools/build_ffmpeg.sh <out dir>        (in an MSYS2 MINGW64 shell; FFMPEG_TAG picks the release, default below)
# Cross-compiling from Linux works too: CROSS=x86_64-w64-mingw32- tools/build_ffmpeg.sh out
set -euo pipefail
TAG="${FFMPEG_TAG:-n8.1.3}"
OUT="$(mkdir -p "${1:-ffmpeg-out}" && cd "${1:-ffmpeg-out}" && pwd)"
SRC="${FFMPEG_SRC:-ffmpeg-src}"

# FFmpeg's official GitHub mirror first (git.ffmpeg.org is often unreachable), the main server as fallback
[ -d "$SRC" ] || git clone --quiet --depth 1 --branch "$TAG" https://github.com/FFmpeg/FFmpeg.git "$SRC" \
  || git clone --quiet --depth 1 --branch "$TAG" https://git.ffmpeg.org/ffmpeg.git "$SRC"
cd "$SRC"
COMMIT="$(git rev-parse HEAD)"

FLAGS=(
  --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug
  --disable-ffplay --disable-ffprobe --enable-ffmpeg
  --disable-avdevice --disable-swscale
  --enable-avformat --enable-avcodec --enable-avfilter --enable-swresample
  --enable-protocol=file
  --enable-demuxer=xwma --enable-decoder=wmav2
  --enable-muxer=wav --enable-encoder=pcm_s16le
  --enable-filter=aresample,aformat,anull,abuffer,abuffersink
  --enable-w32threads --disable-x86asm
  --extra-ldflags=-static --pkg-config-flags=--static
)
if [ -n "${CROSS:-}" ]; then
  FLAGS+=(--enable-cross-compile --target-os=mingw32 --arch=x86_64 --cross-prefix="$CROSS")
fi

./configure "${FLAGS[@]}" > "$OUT/configure.log"
grep -q "^License: LGPL version 2.1 or later" "$OUT/configure.log" \
  || { echo "configure did not report LGPL 2.1+:"; grep -i '^License' "$OUT/configure.log"; exit 1; }
make -j"$(nproc)" ffmpeg.exe > "$OUT/make.log"
"${CROSS:-}strip" -o "$OUT/ffmpeg.exe" ffmpeg.exe
cp LICENSE.md COPYING.LGPLv2.1 "$OUT/"

# only Windows' own DLLs may be needed
DLLS="$("${CROSS:-}objdump" -p "$OUT/ffmpeg.exe" | sed -n 's/^\s*DLL Name: //p' | tr 'A-Z' 'a-z' | sort -u | tr '\n' ' ')"
for d in $DLLS; do
  case "$d" in kernel32.dll|msvcrt.dll|user32.dll|advapi32.dll|shell32.dll|ole32.dll|bcrypt.dll|psapi.dll|ws2_32.dll|api-ms-win-*) ;;
    *) echo "unexpected DLL dependency: $d"; exit 1 ;;
  esac
done

{
  echo "FFmpeg source:  https://github.com/FFmpeg/FFmpeg (official mirror of git.ffmpeg.org)  tag $TAG, commit $COMMIT"
  echo "                https://github.com/FFmpeg/FFmpeg/tree/$COMMIT"
  echo "configure:      ${FLAGS[*]}"
  echo "DLLs used:      $DLLS"
} > "$OUT/build-info.txt"
cat "$OUT/build-info.txt"
ls -l "$OUT/ffmpeg.exe"
