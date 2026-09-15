# Desktop packaging

Distributable builds of **Voca** for macOS (Apple Silicon + Intel)
and Windows. These produce the signed/unsigned installers a website can hand
to users. (Local mac dev: `./build_app.sh` builds the dashboard + py2app alias
app in one step.)

## Layout

| Path | What it does |
| --- | --- |
| `pyinstaller/Voca.spec` | One PyInstaller spec for all three targets. Branches on `sys.platform` / `platform.machine()`: mac → `.app` bundle, Windows → onedir `.exe`. Bundles `dashboard/dist/**` under a `dashboard/` folder; pulls hidden imports + data for faster-whisper, ctranslate2, sounddevice (PortAudio), pywebview, scipy/numpy, pyobjc (mac), pynput/pystray/pywin32 (win), and MLX (Apple Silicon only). Model weights are NOT bundled — downloaded on first run. |
| `pyinstaller/AppIcon.ico` | Windows icon, generated in CI from `assets/AppIcon.iconset/icon_256x256.png`. Not checked in. |
| `macos/dmg.sh` | Builds `Voca-<version>-mac-<arch>.dmg` from the built `.app` (create-dmg if present, else hdiutil). |
| `macos/entitlements.plist` | Hardened-runtime entitlements (mic input + JIT / unsigned-exec-memory / disable-library-validation for Python+MLX). Used only when signing. |
| `windows/installer.iss` | Inno Setup script → `VocaSetup-<version>.exe`. Installs to `Program Files\Voca`, Start Menu shortcut, optional desktop icon, optional "run at login" (HKCU Run key), uninstaller, stable AppId GUID. |
| `../.github/workflows/release.yml` | CI: build + smoke-test (`--selftest`) + package + (optional) sign + publish a Release. |

## Build locally

All commands run from the **repo root**. Build the dashboard first so the UI is
bundled (optional — the spec warns and builds without it if absent). This is an
npm workspaces monorepo (lockfile at root):

```bash
npm ci && npm --workspace dashboard run build
```

For day-to-day macOS use, `./build_app.sh` already does that before packaging
the alias `.app`.

### macOS (arm64 or Intel)

```bash
pip install -r requirements.txt              # Intel mac: requirements-macos-intel.txt
pip install pyinstaller
pyinstaller --noconfirm --clean desktop/pyinstaller/Voca.spec
# smoke test
"dist/Voca.app/Contents/MacOS/Voca" --selftest
# package (arch auto-detected; or pass arm64 / x64)
desktop/macos/dmg.sh
```

### Windows (x64)

```powershell
pip install -r requirements-windows.txt
pip install pyinstaller Pillow
# generate the icon once
python -c "from PIL import Image; Image.open('assets/AppIcon.iconset/icon_256x256.png').convert('RGBA').save('desktop/pyinstaller/AppIcon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
pyinstaller --noconfirm --clean desktop\pyinstaller\Voca.spec
# smoke test
"dist\Voca\Voca.exe" --selftest
# package (needs Inno Setup 6 -> ISCC.exe on PATH or in Program Files)
iscc /DAppVersion=1.0.0 desktop\windows\installer.iss
```

## CI / Releases

`release.yml` triggers on tags `v*` (and manual `workflow_dispatch`). Matrix:
`macos-14` (arm64), `macos-13` (Intel x64), `windows-latest`. Each job builds the
dashboard, freezes with PyInstaller, runs the `--selftest` smoke test, packages,
and uploads an artifact. On a tag push the `release` job publishes a GitHub
Release with both versioned and **stable-named** assets.

### Asset naming contract (website `/api/download`)

The Release always carries these stable names, so a download link never needs to
know the current version. `/api/download?os=...&arch=...` should redirect to the
matching asset on the latest Release:

| Target | Stable asset name |
| --- | --- |
| macOS Apple Silicon | `Voca-mac-arm64.dmg` |
| macOS Intel (x64) | `Voca-mac-x64.dmg` |
| Windows x64 | `VocaSetup-windows-x64.exe` |

Versioned copies are also attached: `Voca-<version>-mac-arm64.dmg`,
`Voca-<version>-mac-x64.dmg`, `VocaSetup-<version>-windows-x64.exe`.

## Signing (optional — builds work UNSIGNED without these)

Signing/notarization steps are present but gated on secrets; add them to enable.

**macOS** (Developer ID + notarization):

| Secret | Value |
| --- | --- |
| `MACOS_CERT_P12` | base64 of the Developer ID Application `.p12` |
| `MACOS_CERT_PASSWORD` | password for that `.p12` |
| `APPLE_ID` | Apple ID email for notarytool |
| `APPLE_TEAM_ID` | 10-char Apple Developer Team ID |
| `APPLE_APP_PASSWORD` | app-specific password for notarytool |

**Windows** (Authenticode):

| Secret | Value |
| --- | --- |
| `WINDOWS_CERT_PFX` | base64 of the code-signing `.pfx` |
| `WINDOWS_CERT_PASSWORD` | password for that `.pfx` |
