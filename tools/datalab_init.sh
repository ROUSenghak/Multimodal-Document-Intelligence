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
{
echo "== $(date -u +%FT%TZ) datalab_init start"

# 1. Claude Code state on the persistent disk: ~/.claude (history, memory, settings, login) and ~/.claude.json.
mkdir -p "$WORK/.claude"
if [ -d "$HOME/.claude" ] && [ ! -L "$HOME/.claude" ]; then
  cp -rn "$HOME/.claude/." "$WORK/.claude/" && rm -rf "$HOME/.claude"
fi
ln -sfn "$WORK/.claude" "$HOME/.claude"
if [ -f "$HOME/.claude.json" ] && [ ! -L "$HOME/.claude.json" ] && [ ! -f "$WORK/.claude.json" ]; then
  mv "$HOME/.claude.json" "$WORK/.claude.json"
fi
[ -f "$WORK/.claude.json" ] && ln -sfn "$WORK/.claude.json" "$HOME/.claude.json"
echo "claude state linked to $WORK/.claude"

# 2. The Claude Code program, installed once into the persistent disk (no sudo needed), then only put on PATH.
NPM_PREFIX="$WORK/.npm-global"
grep -q "$NPM_PREFIX/bin" "$HOME/.bashrc" 2>/dev/null || echo "export PATH=\"$NPM_PREFIX/bin:\$PATH\"" >> "$HOME/.bashrc"
export PATH="$NPM_PREFIX/bin:$PATH"
if command -v claude >/dev/null 2>&1; then
  echo "claude already installed: $(command -v claude)"
elif command -v npm >/dev/null 2>&1; then
  npm config set prefix "$NPM_PREFIX" && npm install -g @anthropic-ai/claude-code && echo "claude installed"
else
  echo "npm not found: install Claude Code by hand once (see the Claude Code documentation)"
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
