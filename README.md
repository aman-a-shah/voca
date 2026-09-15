# 🎙️ Voca

Push-to-talk voice typing that runs **100% on-device**. Hold a key, speak, and
release — your words are transcribed locally and pasted at the cursor in
whatever app you're in. No cloud, no account, no API keys, and **your audio
never leaves your machine.**

**Now cross-platform.** Voca runs on:

- **macOS — Apple Silicon** (M1+): transcription on the GPU via **MLX-Whisper**
  (`large-v3-turbo`), typically **10–20× faster than real time**.
- **macOS — Intel** and **Windows**: transcription on the CPU via
  **faster-whisper** (CTranslate2).

A built-in **dashboard** (recent transcriptions, total words, "time saved,"
activity streaks) is available from the app — all powered by a local-only
history that never leaves your device.

**Download:** get the right build for your machine at **https://getvoca.vercel.app**.

### Privacy & legal

This product's entire identity is privacy: audio is transcribed on-device and
discarded, and the only thing that ever goes over the network is an optional
update check (app version + OS + CPU arch, nothing else — disable with
`DICTATE_NO_UPDATE_CHECK=1`).

- [Privacy Policy](legal/privacy.md)
- [Terms of Use](legal/terms.md)
- [Security Policy](SECURITY.md) — note: current builds are **unsigned**; see it
  for how to open them and verify download checksums.
- [Contributing](CONTRIBUTING.md)
- [Acknowledgements](ACKNOWLEDGEMENTS.md) · [License](LICENSE) (MIT)

> **Push-to-talk key.** On **macOS** the key is **`fn` (🌐 globe)**. On
> **Windows** there is no `fn` key that the OS exposes, so the default is
> **Left Ctrl** (hold) — configurable via `DICTATE_HOTKEY` (e.g. `ctrl_r`,
> `alt_r`, `f8`).

The macOS Apple-Silicon experience is documented in detail below.

---

## Two ways to run it

### 1. As a background app (recommended) — no terminal

```bash
./build_app.sh
```

This installs JS deps, builds the in-app dashboard, and produces
**`dist/Voca.app`** (via py2app). Double-click it: a 🎙️ icon appears in your
menu bar and it runs quietly in the background. macOS asks for **Microphone**
access on first launch — click **Allow**. Then hold `fn`, speak, release —
done. Click the menu-bar icon for status, the last transcription, **Open
Dashboard…**, and **Quit**.

> Built with py2app so macOS attributes Microphone/Accessibility permissions to
> *this app* (a plain shell wrapper hands that identity to the shared system
> Python and the mic prompt never works).

Drag `dist/Voca.app` to **/Applications**, and add it under **System
Settings → General → Login Items** to start it automatically at login.

Menu-bar icon at a glance: ⏳ loading model · 🎙️ ready · 🔴 listening · ✍️
transcribing · ⚠️ needs Accessibility permission.

### 2. In the terminal (for tinkering / config)

```bash
./dictate.sh
```

The first run of either creates a virtualenv, installs dependencies, and
downloads the Whisper model (~1.6 GB, cached afterwards). Then hold **`fn`**,
speak, release — the text appears where your cursor is. `Ctrl-C` to quit.

You'll hear a soft **Tink** when it starts listening and a **Pop** when text is
inserted.

---

## Permissions (one-time)

macOS gates global key capture and synthetic keystrokes behind two permissions:

| Permission | Where | Why |
|---|---|---|
| **Accessibility** | System Settings → Privacy & Security → **Accessibility** | Detect the `fn` key globally and paste text |
| **Microphone** | System Settings → Privacy & Security → **Microphone** | Record while you hold `fn` |

Grant them to whatever launches the engine:

- **App build** → grant to **Voca** (add it under Accessibility; the
  app shows an alert with instructions if it's missing). The mic prompt appears
  the first time you dictate.
- **Terminal** → grant to your terminal app (Terminal, iTerm, your IDE).

After adding Accessibility permission, **quit and relaunch** the app (or
terminal) for it to take effect.

### Stop `fn` from opening the emoji picker

By default macOS may map the globe key to "Show Emoji & Symbols" or "Start
Dictation". For the cleanest experience set it to do nothing:

**System Settings → Keyboard → "Press 🌐 key to" → _Do Nothing_.**

(The engine works regardless — this just stops the OS from also reacting.)

---

## How it works

```
 fn down ──▶ mic stream starts (16 kHz mono, low-latency PortAudio)
 fn up   ──▶ buffer ──▶ trim silence ──▶ MLX-Whisper (GPU) ──▶ paste at cursor
```

Speed comes from a few deliberate choices, all in `dictate/`:

- **Warm model.** The model is loaded and a dummy inference is run at startup, so
  the first real take pays no compile/load tax. (`transcriber.py`)
- **Native-rate capture.** Audio is recorded at Whisper's own 16 kHz, mono, so
  there's no resampling step. (`audio.py`)
- **Silence trimming.** Leading/trailing dead air is gated out before inference,
  which is the single biggest lever on latency. (`transcriber.py`)
- **Off-thread pipeline.** The `fn`-key tap thread only starts/stops the mic;
  transcription and pasting happen on a worker so nothing blocks. (`app.py`)
- **Clipboard paste.** Insertion is a single ⌘V (instant, Unicode-safe) with your
  original clipboard restored a moment later. (`injector.py`)

---

## Smart formatting (polish)

Transcripts get a fast, rule-based cleanup pass before they're inserted. It's
pure regex (~tens of microseconds), so it adds **no perceptible latency** — the
text appears just as fast as before.

Right now it turns spoken enumerations into lists. Say:

> "my grocery list is milk, cheese, and bananas"

and you get:

```
my grocery list:
1. milk
2. cheese
3. bananas
```

It recognises two patterns, both deliberately conservative so normal prose is
never mangled:

- a lead-in with a list word ("list", "steps", "ingredients", "to-dos", …)
  joined to comma-separated items by `:` / "is" / "are" / "includes"
- ordinal enumerations ("first … second … third …")

Ordinary sentences like *"I went to the store and bought milk, cheese, and
bread"* are left exactly as-is. Toggle with `DICTATE_POLISH=0`, switch to bullets
with `DICTATE_LIST_STYLE=bullet`.

## Configuration

Everything is tunable via `DICTATE_*` environment variables — no code edits:

| Variable | Default | Notes |
|---|---|---|
| `DICTATE_BACKEND` | `auto` | Transcription engine. `auto` prefers **MLX** on Apple Silicon and **faster-whisper** elsewhere. Force one with `mlx` or `faster-whisper`. |
| `DICTATE_HOTKEY` | `ctrl_l` (Windows/Intel paths) | Push-to-talk key, using pynput names (`ctrl_l`, `ctrl_r`, `alt_r`, `f8`, …). On macOS Apple Silicon the native `fn`/globe key is used; this applies where the OS doesn't expose `fn`. |
| `DICTATE_HISTORY` | `1` | Local SQLite history that powers the dashboard. Set `0` to record nothing. The history never leaves your device; clear it anytime from the dashboard. |
| `DICTATE_NO_UPDATE_CHECK` | `0` | Set `1` to disable the optional update check entirely (the app's only network activity). |
| `DICTATE_MODEL` | `mlx-community/whisper-large-v3-turbo` | Try `…/whisper-tiny` or `…/whisper-base` for max speed, `…/distil-whisper-large-v3` for a middle ground |
| `DICTATE_LANGUAGE` | `en` | Set `auto` to auto-detect (slightly slower) |
| `DICTATE_INJECT` | `paste` | `type` to emit keystrokes instead (for apps that block paste) |
| `DICTATE_APPEND_SPACE` | `1` | Add a trailing space after each insert |
| `DICTATE_RESTORE_CLIPBOARD` | `1` | Restore your clipboard after pasting |
| `DICTATE_SOUND` | `1` | Audio cues on/off |
| `DICTATE_POLISH` | `1` | Smart formatting (spoken lists → real lists) |
| `DICTATE_LIST_STYLE` | `numbered` | `bullet` for `- item` instead of `1. item` |
| `DICTATE_MIN_LIST_ITEMS` | `2` | Min items before reformatting as a list |
| `DICTATE_MIN_SECONDS` | `0.30` | Ignore taps shorter than this |
| `DICTATE_MAX_SECONDS` | `120` | Safety cap on a single take |

Example — fastest possible, English, no sounds:

```bash
DICTATE_MODEL=mlx-community/whisper-base DICTATE_SOUND=0 ./dictate.sh
```

---

## Testing

```bash
.venv/bin/python tests/test_pipeline.py
```

This synthesizes speech with macOS `say`, runs it through the real model, and
asserts the words come back — no microphone or permissions needed.

---

## Troubleshooting

- **"Could not create event tap"** → Accessibility permission missing; grant it
  and relaunch the terminal.
- **Nothing is pasted** → check Accessibility (for ⌘V) and try
  `DICTATE_INJECT=type`.
- **No audio / empty results** → check Microphone permission and your input
  device in System Settings → Sound.
- **First run is slow** → it's downloading the model once; subsequent runs are
  fast.
- **App doesn't seem to do anything** → check the log at
  `~/Library/Logs/Voca.log`. You want to see
  `fn hotkey installed — ready to dictate`; `BLOCKED` means Accessibility is
  missing. Raw crashes land in `~/Library/Logs/Voca.out.log`.
- **Rebuild after code changes** → re-run `./build_app.sh`, then relaunch the app.

## Requirements

**macOS — Apple Silicon (fastest, GPU via MLX):**

- Apple Silicon Mac (M1 or newer)
- macOS 13+
- Python 3.10+

**macOS — Intel** and **Windows** (CPU via faster-whisper):

- Intel Mac (macOS 13+) or Windows 10/11 (x64)
- Python 3.10+
- On Windows, the WebView2 runtime used by the dashboard ships with Windows
  10/11.

Use the requirements file for your platform: `requirements.txt` (Apple
Silicon), `requirements-macos-intel.txt` (Intel Mac), or
`requirements-windows.txt` (Windows). Shared deps live in
`requirements-base.txt`.
