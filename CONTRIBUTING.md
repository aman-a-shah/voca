# Contributing to Voca

Thanks for your interest in improving Voca. This is a privacy-first,
100%-on-device dictation app, and that principle is non-negotiable: **no
contribution should send user audio, transcripts, or personal data off the
device, or add tracking/analytics.** Beyond that, contributions of all kinds are
welcome.

## Repository layout

| Path | What lives here |
|---|---|
| `dictate/` | The Python transcription engine: audio capture, push-to-talk hotkey, backends (MLX / faster-whisper), text injection, local history (`store.py`), update check (`updater.py`), and platform-specific code under `dictate/platforms/`. |
| `web/` | The marketing/download website (the public surface). |
| `dashboard/` | The in-app dashboard UI (recent transcriptions, stats), hosted in a native webview. |
| `desktop/` | Desktop packaging and installer/build configuration. |
| `packages/ui` | Shared design system / tokens reused by both the website and the dashboard. |
| `tests/` | Tests (see below). |

## Running it locally

### The engine (macOS dev build)

```bash
./build_app.sh
```

This builds the dashboard UI and the macOS menu-bar app in one step. For quick
iteration in a terminal (with `DICTATE_*` config), use `./dictate.sh`. The first
run creates a virtualenv, installs dependencies (Python + npm), and downloads
the Whisper model (~1.6 GB, cached afterward).

> One install only: build and run the `/Applications` copy. Do not run a signed
> duplicate out of `dist/` — on macOS that creates a second bundle that hijacks
> the microphone/accessibility permissions and breaks paste.

### The website / shared UI

```bash
cd web && npm install && npm run dev
```

(Use the equivalent in `dashboard/` and `packages/ui` as needed.)

### Tests

```bash
.venv/bin/python tests/test_pipeline.py
```

The pipeline test synthesizes speech with macOS `say`, runs it through the real
model, and asserts the words come back — no microphone or permissions needed.
Please run the relevant tests before opening a PR, and add tests for new
behavior where practical.

## Coding conventions

- **Match the existing style.** The Python code uses type hints,
  `from __future__ import annotations`, dataclasses for config, and small,
  well-commented modules. Mirror what's already there rather than introducing a
  new style.
- Keep the hot path fast: transcription and injection run off the UI/hotkey
  thread, and the hotkey tap must stay cheap (see the engine comments).
- Make new behavior **configurable via `DICTATE_*` environment variables**
  rather than hard-coded, following the pattern in `dictate/config.py`.
- Don't add network calls. The only sanctioned network activity is the existing
  update check.

## Submitting changes

1. Fork and create a topic branch.
2. Make focused commits with clear messages.
3. Run the relevant tests and dev build.
4. Open a pull request describing **what** changed and **why**, plus how you
   tested it. Note any new `DICTATE_*` variables so they can be documented.

By contributing, you agree that your contributions are licensed under the
project's MIT License (see `LICENSE`).

## Releases

Releases are tag-driven. Pushing a version tag (`v*`, e.g. `v1.2.0`) triggers
CI to build the platform artifacts and publish the release. Each release
includes **SHA-256 checksums** for the downloads (see `SECURITY.md`). Current
builds are not yet code-signed; signing is planned.

## Reporting bugs and security issues

- **Bugs / features:** open an issue at **https://github.com/aman-a-shah/voca**.
- **Security vulnerabilities:** do **not** open a public issue — follow
  `SECURITY.md`.
