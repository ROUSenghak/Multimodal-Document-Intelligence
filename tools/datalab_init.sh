#!/bin/bash
# Start-up script for an Onyxia VS Code service (ENSAE-ENSAI Datalab / SSP Cloud).
#
# Why: a paused or restarted service keeps only /home/onyxia/work. This restores, at every start, what lives
# outside it: Claude Code (program, login, chat history, memory), the VS Code extensions and the Jupyter kernel.
# How: set this file's raw GitHub URL as the service's "personalInit" script (see docs/ssp_cloud.md §2.7).
# Every step is logged to ~/work/.datalab_init.log; nothing here prints or stores a secret.
set -u
WORK=/home/onyxia/work
REPO="$WORK/Multimodal-Document-Intelligence"
LOG="$WORK/.datalab_init.log"
mkdir -p "$WORK"
add_to_bashrc() { grep -qxF "$1" "$HOME/.bashrc" 2>/dev/null || echo "$1" >> "$HOME/.bashrc"; }
{
echo "== $(date -u +%FT%TZ) datalab_init start"

# 1. Claude Code state on the persistent disk. CLAUDE_CONFIG_DIR moves all of it there (settings, login, chat
#    history, memory and the .claude.json file); ~/.claude is linked to the same folder for tools that look there.
CONFIG="$WORK/.claude"
mkdir -p "$CONFIG"
if [ -d "$HOME/.claude" ] && [ ! -L "$HOME/.claude" ]; then
  cp -rn "$HOME/.claude/." "$CONFIG/" && rm -rf "$HOME/.claude"
fi
ln -sfn "$CONFIG" "$HOME/.claude"
[ -f "$WORK/.claude.json" ] && [ ! -f "$CONFIG/.claude.json" ] && mv "$WORK/.claude.json" "$CONFIG/.claude.json"
add_to_bashrc "export CLAUDE_CONFIG_DIR=\"$CONFIG\""
export CLAUDE_CONFIG_DIR="$CONFIG"
echo "claude state kept in $CONFIG"

# 2. The Claude Code program. This image has no npm, so use the official installer, which needs no sudo. It puts
#    the program in ~/.local/share/claude/versions/<version> and the command ~/.local/bin/claude. That folder is
#    kept on the persistent disk, so the installer runs only once; later starts only recreate the links.
PROGRAM="$WORK/.claude-program"
mkdir -p "$PROGRAM" "$HOME/.local/share" "$HOME/.local/bin"
if [ -d "$HOME/.local/share/claude" ] && [ ! -L "$HOME/.local/share/claude" ]; then
  cp -rn "$HOME/.local/share/claude/." "$PROGRAM/" && rm -rf "$HOME/.local/share/claude"
fi
ln -sfn "$PROGRAM" "$HOME/.local/share/claude"
add_to_bashrc 'export PATH="$HOME/.local/bin:$PATH"'
export PATH="$HOME/.local/bin:$PATH"
latest=$(ls "$PROGRAM/versions" 2>/dev/null | sort -V | tail -1)
if [ -n "$latest" ]; then
  ln -sfn "$PROGRAM/versions/$latest" "$HOME/.local/bin/claude" && echo "claude $latest ready (kept in $PROGRAM)"
elif curl -fsSL https://claude.ai/install.sh | bash; then
  echo "claude installed: $(ls "$PROGRAM/versions" 2>/dev/null | sort -V | tail -1)"
else
  echo "claude install FAILED: run 'curl -fsSL https://claude.ai/install.sh | bash' in a terminal"
fi

# 3. VS Code extensions (reinstalled at each start; they live outside ~/work).
if command -v code-server >/dev/null 2>&1; then
  for ext in ms-python.python ms-toolsai.jupyter; do
    code-server --install-extension "$ext" >/dev/null 2>&1 && echo "extension ok: $ext" || echo "extension FAILED: $ext"
  done
else
  echo "code-server not found: extensions not installed"
fi

# 4. The project's Jupyter kernel, if the project's .venv already exists (it lives in ~/work, so it survives).
if [ -x "$REPO/.venv/bin/python" ]; then
  "$REPO/.venv/bin/python" -m ipykernel install --user --name visualdoc-venv --display-name "VisualDoc (.venv, Python 3.12)" \
    && echo "kernel visualdoc-venv registered"
else
  echo "no $REPO/.venv yet: create it once (docs/ssp_cloud.md §2.6), the next start registers the kernel"
fi

echo "== $(date -u +%FT%TZ) datalab_init done"
} >> "$LOG" 2>&1
exit 0
