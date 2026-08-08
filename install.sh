#!/usr/bin/env bash
# Put git-heatmap on PATH so git picks it up as `git heatmap`.
#
#   ./install.sh                              symlink into ~/.local/bin
#   ./install.sh --prefix /usr/local/bin      somewhere else
#   ./install.sh --copy                       copy instead of symlink
#
# Symlinking is the default so edits in this repo take effect with no reinstall.

set -euo pipefail

PREFIX="${HOME}/.local/bin"
MODE="symlink"
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/git-heatmap"

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
    --copy)   MODE="copy"; shift ;;
    -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -f "$SOURCE" ] || { echo "install.sh: cannot find $SOURCE" >&2; exit 1; }
command -v git >/dev/null || echo "install.sh: warning: git is not on PATH" >&2
command -v python3 >/dev/null || { echo "install.sh: python3 is required" >&2; exit 1; }

mkdir -p "$PREFIX"
TARGET="${PREFIX}/git-heatmap"

if [ "$MODE" = "copy" ]; then
  install -m 755 "$SOURCE" "$TARGET"
else
  ln -sfn "$SOURCE" "$TARGET"
  chmod +x "$SOURCE"
fi

echo "installed: $TARGET -> $([ -L "$TARGET" ] && readlink "$TARGET" || echo "(copy)")"

case ":${PATH}:" in
  *":${PREFIX}:"*) ;;
  *) echo "install.sh: warning: ${PREFIX} is not on your PATH; add it to use \`git heatmap\`" >&2 ;;
esac

echo "try: git heatmap -h"
