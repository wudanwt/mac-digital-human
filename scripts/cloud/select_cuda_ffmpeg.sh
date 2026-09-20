#!/usr/bin/env bash
# Source this file from CUDA Worker launch/check scripts.
# It never installs packages. It only selects an already-installed FFmpeg
# binary that can actually complete an h264_nvenc smoke encode.

_cuda_ffmpeg_nvenc_usable() {
  local bin="$1"
  [ -x "$bin" ] || return 1
  "$bin" -hide_banner -encoders 2>/dev/null | grep -q 'h264_nvenc' || return 1
  "$bin" -hide_banner -loglevel error \
    -f lavfi -i 'color=c=black:s=64x64:r=25:d=0.04' \
    -frames:v 1 -c:v h264_nvenc -f null - \
    >/dev/null 2>&1
}

_cuda_ffmpeg_add_candidate() {
  local value="$1"
  [ -n "$value" ] || return 0
  [ -x "$value" ] || return 0
  local existing
  for existing in "${CUDA_FFMPEG_CANDIDATES[@]:-}"; do
    [ "$existing" = "$value" ] && return 0
  done
  CUDA_FFMPEG_CANDIDATES+=("$value")
}

CUDA_FFMPEG_CANDIDATES=()

if [ -n "${FFMPEG_BIN:-}" ]; then
  _cuda_ffmpeg_add_candidate "$FFMPEG_BIN"
fi

_current_ffmpeg="$(command -v ffmpeg 2>/dev/null || true)"
_cuda_ffmpeg_add_candidate "$_current_ffmpeg"
_cuda_ffmpeg_add_candidate /usr/bin/ffmpeg
_cuda_ffmpeg_add_candidate /usr/local/bin/ffmpeg
_cuda_ffmpeg_add_candidate /opt/ffmpeg/bin/ffmpeg

CUDA_SELECTED_FFMPEG=""
CUDA_SELECTED_FFMPEG_NVENC=0

for _candidate in "${CUDA_FFMPEG_CANDIDATES[@]:-}"; do
  if _cuda_ffmpeg_nvenc_usable "$_candidate"; then
    CUDA_SELECTED_FFMPEG="$_candidate"
    CUDA_SELECTED_FFMPEG_NVENC=1
    break
  fi
done

if [ -z "$CUDA_SELECTED_FFMPEG" ]; then
  CUDA_SELECTED_FFMPEG="${FFMPEG_BIN:-${_current_ffmpeg:-}}"
fi

if [ -z "$CUDA_SELECTED_FFMPEG" ] || [ ! -x "$CUDA_SELECTED_FFMPEG" ]; then
  echo "ERROR: no usable FFmpeg executable was found." >&2
  return 2 2>/dev/null || exit 2
fi

export FFMPEG_BIN="$CUDA_SELECTED_FFMPEG"
export CUDA_SELECTED_FFMPEG
export CUDA_SELECTED_FFMPEG_NVENC

_ffmpeg_dir="$(dirname "$CUDA_SELECTED_FFMPEG")"
case ":$PATH:" in
  *":$_ffmpeg_dir:"*) ;;
  *) export PATH="$_ffmpeg_dir:$PATH" ;;
esac
# If the shell cached another ffmpeg path before PATH changed, clear it.
hash -r 2>/dev/null || true

if [ "$CUDA_SELECTED_FFMPEG_NVENC" = "1" ]; then
  echo "CUDA FFmpeg selected: $CUDA_SELECTED_FFMPEG (NVENC usable)"
else
  echo "CUDA FFmpeg selected: $CUDA_SELECTED_FFMPEG (NVENC NOT usable)" >&2
  if [ "${CUDA_REQUIRE_NVENC:-0}" = "1" ]; then
    echo "ERROR: CUDA_REQUIRE_NVENC=1 but no installed FFmpeg can use h264_nvenc." >&2
    return 3 2>/dev/null || exit 3
  fi
fi

unset _candidate _current_ffmpeg _ffmpeg_dir
