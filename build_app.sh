#!/usr/bin/env bash
# Build "Voca.app" with py2app (alias mode), including the in-app dashboard.
#
# Why py2app instead of a shell-script wrapper: macOS attributes Microphone and
# Accessibility permissions to the *bundle whose executable the OS launched*. A
# script that re-execs the framework Python hands that identity to the shared
# Python.app, so permission prompts never attribute to our app. py2app installs a
# real native bootloader as the bundle's main executable, so TCC sees "Voca"
# and the mic prompt works. Alias mode references this project/venv in
# place (fast, not relocatable) — perfect for personal use.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${PROJECT_DIR}"

# --- Dashboard UI (needed for Open Dashboard…) ------------------------------
# This is an npm workspaces monorepo: the only lockfile is at the repo root.
# `npm --prefix dashboard ci` fails — install from root, then build the workspace.
if ! command -v npm >/dev/null 2>&1; then
  echo "❌ Node.js/npm is required to build the dashboard UI."
  echo "   Install from https://nodejs.org (or via nvm/brew), then re-run ./build_app.sh"
  exit 1
fi

if [[ ! -d node_modules ]]; then
  echo "Installing JS dependencies…"
  npm ci
fi

echo "Building dashboard…"
npm --workspace dashboard run build

# --- Ensure the venv + deps exist -------------------------------------------
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Setting up virtualenv…"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip wheel >/dev/null
fi
# py2app + runtime deps (idempotent; quick once cached).
.venv/bin/python -m pip install -q -r requirements.txt py2app

echo "Building Voca.app…"
rm -rf build dist
# Remove the obsolete shell-wrapper bundle if present.
rm -rf "Voca.app"

.venv/bin/python setup.py py2app -A >/tmp/voca-py2app.log 2>&1 \
  || { echo "Build failed — see /tmp/voca-py2app.log"; tail -20 /tmp/voca-py2app.log; exit 1; }

APP="${PROJECT_DIR}/dist/Voca.app"
echo
echo "✅ Built: ${APP}"
echo
echo "Next:"
echo "  1. Double-click it (a 🎙️ appears in your menu bar)."
echo "  2. Click Allow when macOS asks for Microphone access."
echo "  3. If the fn key does nothing, add 'Voca' under System Settings"
echo "     → Privacy & Security → Accessibility, then relaunch."
echo "  4. Hold fn, speak, release — text lands at your cursor."
echo "  5. Menu bar → Open Dashboard… for history and stats."
echo
echo "Tip: drag dist/Voca.app to /Applications, and add it to System"
echo "     Settings → General → Login Items to launch at startup."
echo "Logs: ~/Library/Logs/Voca.log"
