"""Background menu-bar app — no terminal required.

Launches as a macOS *accessory* app: a single 🎙️ icon lives in the menu bar
(no Dock icon, no window). The fn key works system-wide exactly as in the CLI;
this just renders the engine's state as the menu-bar glyph and a status line, and
gives you a Quit item.

Runs on AppKit's NSApplication run loop. The fn event-tap source is installed on
that same main run loop, and engine state changes (which originate on worker
threads) are marshalled back to the main thread before touching any UI.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
import threading
import time

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSAlert,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSFontWeightRegular,
    NSFontWeightSemibold,
    NSGlassEffectView,
    NSImage,
    NSImageLeft,
    NSImageSymbolConfiguration,
    NSLineBreakByTruncatingTail,
    NSPanel,
    NSPopUpMenuWindowLevel,
    NSScreen,
    NSStatusBar,
    NSTextAlignmentLeft,
    NSTextField,
    NSView,
    NSVariableStatusItemLength,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorTransient,
    NSWindowStyleMaskBorderless,
    NSWorkspace,
)
from Foundation import (
    NSAttributedString,
    NSMakePoint,
    NSMakeRect,
    NSMakeSize,
    NSObject,
    NSRunLoopCommonModes,
)

from .config import CONFIG
from .core import DictationEngine
from .hotkey import FnHotkey
from .overlay import Overlay

_LOG_PATH = os.path.expanduser("~/Library/Logs/Voca.log")


def _log(message: str) -> None:
    """Append a line to the app log (the app has no console when launched via Finder)."""
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except OSError:
        pass


def _traceback() -> str:
    import traceback

    return traceback.format_exc()


def _arm_deadman(seconds: float) -> None:
    """Force a clean process exit after ``seconds``, regardless of what is wedged.

    A daemon timer that calls ``os._exit(0)`` so a stuck background worker (a hung
    paste, a CoreAudio open that never returns, a thread pool that won't drain) can
    never keep the app from quitting. ``os._exit`` is deliberate: it bypasses the
    interpreter shutdown / thread-join that both crashes the app (native threads
    racing exit) and hangs it (concurrent.futures' atexit handler joining a wedged
    worker). If the clean teardown finishes first we ``os._exit`` before this
    fires; the timer is a daemon, so it never keeps the process alive on its own."""
    def _fire():
        _log("deadman: teardown didn't finish in time — force-exiting")
        os._exit(0)

    timer = threading.Timer(seconds, _fire)
    timer.daemon = True
    timer.start()


# Menu-bar icon per engine state. Rendered as monochrome SF Symbol *template*
# images so they sit natively in the menu bar (auto-tinting for light/dark,
# matching the system's own icons) instead of a loud emoji. A `waveform` mark
# reads instantly as "voice"; the busy/recording/error states vary it subtly.
# "ld.waveform" is our OWN 4-bar mark (drawn below), not an SF Symbol: Apple's
# `waveform` symbol has many bars and reads as a *different* logo than the app
# icon's 4-bar waveform (assets/make_icon.py). The idle/ready glyph — the one
# parked in the menu bar whenever the app is running — uses ours so it matches.
_SYMBOL = {
    "loading": "ellipsis",                 # warming the model
    "ready": "ld.waveform",                # idle, waiting for fn (our 4-bar mark)
    "listening": "mic.fill",               # recording your voice
    "transcribing": "ellipsis",            # model is thinking
    "error": "exclamationmark.triangle",   # something went wrong
    "blocked": "exclamationmark.triangle",  # missing a permission
}

# The app icon's 4-bar waveform on a 32-unit grid (identical to make_icon.py and
# the website/dashboard Logo): bar centers + heights, bar width.
_WAVE_CENTERS = (8, 13, 18, 23)
_WAVE_HEIGHTS = (11, 6, 18, 9)
_WAVE_BAR_W = 2.8

# Emoji fallback if SF Symbols aren't available (very old macOS).
_GLYPH = {
    "loading": "⏳",
    "ready": "🎙️",
    "listening": "🔴",
    "transcribing": "✍️",
    "error": "⚠️",
    "blocked": "⚠️",
}

_SYMBOL_CACHE: dict = {}


def _waveform_image():
    """Our 4-bar waveform as a template NSImage, matching the macOS app icon.

    Drawn (not an SF Symbol) because Apple's `waveform` symbol has many bars and
    reads as a different mark. Template image → the menu bar tints it for
    light/dark like a native glyph. Resolution-independent (the handler redraws
    per backing scale), so it stays crisp on Retina. Cached.
    """
    if "ld.waveform" in _SYMBOL_CACHE:
        return _SYMBOL_CACHE["ld.waveform"]

    pad = 1.0
    scale = 14.0 / max(_WAVE_HEIGHTS)        # tallest bar (18u) -> 14 pt
    bar_w = _WAVE_BAR_W * scale
    left_edge = _WAVE_CENTERS[0] - _WAVE_BAR_W / 2.0
    cluster_w = ((_WAVE_CENTERS[-1] + _WAVE_BAR_W / 2.0) - left_edge) * scale
    width = cluster_w + 2 * pad
    height = 16.0
    cy = height / 2.0

    def _draw(_rect):
        try:
            NSColor.blackColor().setFill()  # template: only the shape matters
            for cx, h in zip(_WAVE_CENTERS, _WAVE_HEIGHTS):
                bh = h * scale
                x = pad + ((cx - _WAVE_BAR_W / 2.0) - left_edge) * scale
                y = cy - bh / 2.0
                rect = NSMakeRect(x, y, bar_w, bh)
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    rect, bar_w / 2.0, bar_w / 2.0
                ).fill()
        except Exception:
            return False
        return True

    image = None
    try:
        image = NSImage.imageWithSize_flipped_drawingHandler_(
            NSMakeSize(width, height), False, _draw
        )
        if image is not None:
            image.setTemplate_(True)
    except Exception:
        image = None
    _SYMBOL_CACHE["ld.waveform"] = image
    return image


def _symbol_image(name, point_size=15.0):
    """A template NSImage (cached), or None if unavailable.

    ``ld.waveform`` is our own drawn 4-bar mark; everything else is an SF Symbol.
    The menu-bar glyph wants 15pt; button labels want to match their 13pt text,
    so the size is part of the cache key.
    """
    if name == "ld.waveform":
        return _waveform_image()
    key = (name, point_size)
    if key in _SYMBOL_CACHE:
        return _SYMBOL_CACHE[key]
    image = None
    try:
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if image is not None:
            cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
                point_size, NSFontWeightRegular
            )
            image = image.imageWithSymbolConfiguration_(cfg) or image
            image.setTemplate_(True)  # let the host tint it (light/dark)
    except Exception:
        image = None
    _SYMBOL_CACHE[key] = image
    return image


# Panel metrics lifted from Intermission's SwiftUI menu, so our three menu-bar
# apps drop the same translucent panel: 244pt wide, 12pt padding, 12pt between
# blocks, 3pt between the two header lines. AppKit has no VStack, so the rows
# below are laid out by hand against these numbers.
_PANEL_WIDTH = 244
_PANEL_PAD = 12
_PANEL_GAP = 12
_HEADER_GAP = 3
_TITLE_H = 16  # one line of 13pt semibold
_CAPTION_H = 15  # one line of 12pt regular
_PANEL_CORNER = 14  # glass corner radius, as a MenuBarExtra window draws it
_PANEL_MENU_GAP = 7  # drop below the menu bar, level with a MenuBarExtra window
# Clicking the status item while the panel is open makes it resign key, which
# closes it — and the click would then immediately reopen it. Ignore a reopen
# that lands within this window so the item toggles instead of flickering.
_PANEL_REOPEN_GUARD = 0.25


_BUTTON_H = 25
_BUTTON_RADIUS = 6.0
_BUTTON_FILL_ALPHA = 0.08
_BUTTON_PAD_X = 11  # per side; nets 13pt to the glyph, measured off Intermission's buttons


class _ButtonRow(NSView):
    """Paints SwiftUI's bordered-button fill behind a borderless button.

    AppKit's rounded bezel is a white pill with an outline and a drop shadow;
    SwiftUI's is a flat rounded rect of the label colour at 8% alpha (measured
    off Intermission's panel), and that is what reads as a solid rectangle
    against the glass. Painting it here rather than as a layer colour keeps
    light/dark correct, since the dynamic colour resolves at draw time.

    The fill lives on this wrapper instead of on the button because NSButton
    pins its image to the leading edge whatever the alignment, so padding the
    button's own frame leaves the icon flush against the fill. Insetting the
    button inside a wrapper is the only way to get SwiftUI's even padding.
    """

    def drawRect_(self, rect):  # noqa: N802
        NSColor.labelColor().colorWithAlphaComponent_(_BUTTON_FILL_ALPHA).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), _BUTTON_RADIUS, _BUTTON_RADIUS
        ).fill()

    def mouseDown_(self, event):  # noqa: N802
        """Keep the whole pill clickable, not just the inset button."""
        subviews = self.subviews()
        if subviews:
            subviews[0].performClick_(None)


class _GlassPanel(NSPanel):
    """A borderless panel that can still take key focus.

    Borderless windows refuse key by default, and without key focus there is no
    resign-key notification — which is the only dismissal a panel gets, since
    unlike NSPopover it has no light-dismiss of its own. A global mouse monitor
    would need Accessibility trust and still miss synthetic clicks.
    """

    def canBecomeKeyWindow(self):  # noqa: N802
        return True


class DictationController(NSObject):
    def initWithEngine_(self, engine):  # noqa: N802 (ObjC selector form)
        self = objc.super(DictationController, self).init()
        if self is None:
            return None
        self.engine = engine
        self.statusItem = None
        self.stateItem = None
        self.lastItem = None
        self.modelItem = None
        self.panel = None
        self._panel_closed_at = 0.0
        self.hotkey = None
        self.overlay = None
        self._pending = []  # (state, info) queued from worker threads
        self._pending_lock = threading.Lock()
        return self

    # -- UI construction (main thread) --------------------------------------
    @objc.python_method
    def build(self):
        bar = NSStatusBar.systemStatusBar()
        self.statusItem = bar.statusItemWithLength_(NSVariableStatusItemLength)
        self._glyph("loading")
        button = self.statusItem.button()
        if button is not None:
            button.setTarget_(self)
            button.setAction_("toggleMenu:")
            button.setToolTip_("Voca")

        self._build_panel()

        # Heads-up voice overlay that drops from the camera notch while you hold fn.
        self.overlay = Overlay.alloc().initWithLevelProvider_(
            lambda: self.engine.recorder.level
        )
        self.overlay.build()

    @objc.python_method
    def _build_panel(self):
        """The menu-bar panel — a translucent popover matching Intermission's.

        Rows are declared top-down as (view, width, height, gap-above); the gap
        on the first row is the top padding. Their total plus one bottom padding
        is the panel height, which then flips each row's top offset into
        AppKit's bottom-left origin.
        """
        inner = _PANEL_WIDTH - (_PANEL_PAD * 2)

        self.stateItem = self._label("Voca is warming up", 13, NSFontWeightSemibold)
        self.lastItem = self._label("Last: —", 12, NSFontWeightRegular, secondary=True)
        self.lastItem.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        self.modelItem = self._label(
            f"Model: {CONFIG.model.split('/')[-1]}", 12, NSFontWeightRegular, secondary=True
        )
        dashboard = self._button("Open Dashboard…", "rectangle.grid.2x2", "openDashboard:")
        quit_button = self._button("Quit Voca", "power", "quitApp:")

        def button_row(button, gap):
            # Buttons keep the size they hugged their label to, so they read as
            # discrete pills like SwiftUI's rather than full-width bars.
            size = button.frame().size
            return (button, size.width, size.height, gap)

        rows = [
            (self.stateItem, inner, _TITLE_H, _PANEL_PAD),
            (self.lastItem, inner, _CAPTION_H, _HEADER_GAP),
            (self._divider(), inner, 1, _PANEL_GAP),
            button_row(dashboard, _PANEL_GAP),
            (self._divider(), inner, 1, _PANEL_GAP),
            (self.modelItem, inner, _CAPTION_H, _PANEL_GAP),
            button_row(quit_button, _PANEL_GAP),
        ]

        height = sum(h + gap for _, _, h, gap in rows) + _PANEL_PAD
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, _PANEL_WIDTH, height))

        top = height
        for child, w, h, gap in rows:
            top -= gap + h
            child.setFrame_(NSMakeRect(_PANEL_PAD, top, w, h))
            view.addSubview_(child)

        # A borderless panel filled with glass, rather than an NSPopover: only
        # this gets the same Liquid Glass material and square-cornered, arrowless
        # shape as a SwiftUI MenuBarExtra window. A popover draws the older
        # arrowed chrome and anchors itself over the menu bar.
        glass = NSGlassEffectView.alloc().initWithFrame_(
            NSMakeRect(0, 0, _PANEL_WIDTH, height)
        )
        glass.setCornerRadius_(_PANEL_CORNER)
        glass.setContentView_(view)

        self.panel = _GlassPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _PANEL_WIDTH, height),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self.panel.setContentView_(glass)
        self.panel.setDelegate_(self)  # for windowDidResignKey_
        self.panel.setOpaque_(False)  # let the glass show what's behind it
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setLevel_(NSPopUpMenuWindowLevel)  # above ordinary windows
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorTransient
        )

    @objc.python_method
    def _label(self, title, size, weight, secondary=False):
        label = NSTextField.labelWithString_(title)
        label.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
        label.setAlignment_(NSTextAlignmentLeft)
        if secondary:
            label.setTextColor_(NSColor.secondaryLabelColor())
        return label

    @objc.python_method
    def _button(self, title, symbol, action):
        """A filled rounded rect sized to its label, with a leading SF Symbol.

        Returns the wrapper that paints the fill, with the button inset inside
        it — see _ButtonRow for why the fill can't live on the button itself.
        """
        button = NSButton.buttonWithTitle_target_action_(title, self, action)
        button.setBordered_(False)  # the fill is drawn by _ButtonRow
        font = NSFont.systemFontOfSize_weight_(13, NSFontWeightRegular)
        button.setFont_(font)
        # A borderless button dims its own title and icon; SwiftUI's sit at full
        # label colour. Spell both out so they match.
        button.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(
                title,
                {
                    NSForegroundColorAttributeName: NSColor.labelColor(),
                    NSFontAttributeName: font,
                },
            )
        )
        image = _symbol_image(symbol, point_size=13.0)
        if image is not None:
            button.setImage_(image)
            button.setImagePosition_(NSImageLeft)
            button.setContentTintColor_(NSColor.labelColor())
        # Hug the label, then centre it in a fill padded to SwiftUI's proportions.
        button.sizeToFit()
        size = button.frame().size
        row = _ButtonRow.alloc().initWithFrame_(
            NSMakeRect(0, 0, size.width + (_BUTTON_PAD_X * 2), _BUTTON_H)
        )
        button.setFrame_(
            NSMakeRect(
                _BUTTON_PAD_X, (_BUTTON_H - size.height) / 2.0, size.width, size.height
            )
        )
        row.addSubview_(button)
        return row

    @objc.python_method
    def _divider(self):
        divider = NSBox.alloc().init()
        divider.setBoxType_(NSBoxSeparator)
        return divider

    def toggleMenu_(self, _):  # noqa: N802
        if self.panel is None or self.statusItem is None:
            return
        if self.panel.isVisible():
            self._close_panel()
        elif time.monotonic() - self._panel_closed_at >= _PANEL_REOPEN_GUARD:
            self._open_panel()

    def windowDidResignKey_(self, _notification):  # noqa: N802
        """Clicking anywhere else takes key away — that's our light-dismiss."""
        self._close_panel()

    @objc.python_method
    def _open_panel(self):
        """Hang the panel under the menu-bar item, clamped to the screen."""
        button = self.statusItem.button()
        window = button.window() if button is not None else None
        if window is None:
            return
        item = window.convertRectToScreen_(button.convertRect_toView_(button.bounds(), None))
        size = self.panel.frame().size

        x = item.origin.x + (item.size.width - _PANEL_WIDTH) / 2.0
        y = item.origin.y - size.height - _PANEL_MENU_GAP
        visible = (window.screen() or NSScreen.mainScreen()).visibleFrame()
        # Keep it fully on screen when the item sits near a corner.
        x = max(
            visible.origin.x + 8,
            min(x, visible.origin.x + visible.size.width - _PANEL_WIDTH - 8),
        )
        self.panel.setFrameOrigin_(NSMakePoint(x, y))
        # Taking key focus is what arms the resign-key dismissal below; an
        # accessory app has to activate itself to get it.
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _close_panel(self):
        if self.panel is not None and self.panel.isVisible():
            self.panel.orderOut_(None)
        self._panel_closed_at = time.monotonic()

    # -- app delegate: fires once the app is fully launched & able to show UI -
    def applicationDidFinishLaunching_(self, _notification):  # noqa: N802
        try:
            self.build()
            self._ensure_mic()  # now the system can actually present the prompt
            # Use a module-level plain function as the thread target: invoking an
            # @objc.python_method from a fresh thread is unreliable under the
            # py2app/pyobjc runtime, but plain functions thread fine.
            threading.Thread(target=_do_warmup, args=(self,), daemon=True).start()
        except Exception:
            import traceback
            _log("FATAL in applicationDidFinishLaunching:\n" + traceback.format_exc())

    @objc.python_method
    def _ensure_mic(self):
        # PortAudio won't reliably prompt for mic access, so do it explicitly here
        # (otherwise the app silently records zeros -> "nothing recognized").
        from . import permissions

        status = permissions.mic_status()
        _log(f"microphone permission: {permissions.mic_status_name()}")
        if status == permissions.DENIED:
            # macOS won't prompt again once denied — user must flip it manually.
            self._show_state("blocked", "Enable Microphone in System Settings")
            self._alert(
                "Microphone access is off",
                "Voca needs the microphone to hear you. Turn it on under "
                "System Settings → Privacy & Security → Microphone, then relaunch.",
            )
        elif status != permissions.AUTHORIZED:
            def done(granted):
                _log(f"microphone access granted: {bool(granted)}")

            permissions.request_mic(done)

    def installHotkey_(self, _):  # noqa: N802
        from . import permissions

        # Posting ⌘V to paste needs Accessibility — a *different* grant from the
        # one that lets us hear the fn key. If it's missing, the fn key still
        # triggers transcription but the paste is silently dropped.
        trusted = permissions.accessibility_trusted()
        _log(f"accessibility trusted (can paste): {trusted}")
        if not trusted:
            permissions.request_accessibility()  # opens the System Settings deep-link
            self._alert(
                "One more permission needed",
                "Voca can hear the fn key but can't paste text yet. "
                "Add it under System Settings → Privacy & Security → Accessibility "
                "(toggle it ON), then quit and relaunch the app.",
            )

        self.hotkey = FnHotkey(
            self.engine.on_press,
            self.engine.on_release,
            log=_log,
            max_hold_seconds=CONFIG.max_record_seconds,
        )
        try:
            # Run the tap on its own thread/run loop, not the main one — the main
            # run loop drives the 60 fps overlay, and sharing it lets that drawing
            # starve the tap so macOS disables it and drops fn presses/releases
            # (the intermittent "chopped into empty fragments" failure).
            self.hotkey.start_background()
            self._observe_wake()  # re-arm the tap the instant the Mac wakes
            _log("fn hotkey installed on dedicated thread — ready to dictate")
        except PermissionError as exc:
            _log(f"BLOCKED: {exc}")
            self._show_state("blocked", "Needs Accessibility permission")
            self._alert(
                "Accessibility permission needed",
                f"{exc}\n\nAdd “Voca” under System Settings → Privacy & "
                "Security → Accessibility, then quit and relaunch the app.",
            )

    @objc.python_method
    def _observe_wake(self):
        """Re-enable the fn tap the moment the Mac wakes from sleep.

        A CGEventTap is frequently disabled across a sleep/wake cycle, and the
        disable event isn't always delivered — the watchdog catches that within a
        second or two, but waking the tap on the wake notification makes recovery
        instant so the first fn press after opening the lid already works.
        """
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self, "systemDidWake:", "NSWorkspaceDidWakeNotification", None
        )

    def systemDidWake_(self, _notification):  # noqa: N802 (main thread)
        if self.hotkey is not None:
            self.hotkey.reenable()

    # -- engine state bridge (callable from any thread) ---------------------
    @objc.python_method
    def onEngineState(self, state, info):
        # Keep all data as native Python objects (no ObjC bridging of dicts);
        # just wake the main thread to drain the queue.
        with self._pending_lock:
            self._pending.append((state, dict(info) if info else {}))
        # Deliver in *common* modes so the state (and the overlay it shows) lands
        # even while the run loop is in a tracking mode — e.g. the status-bar menu
        # is open — instead of stalling until the loop returns to its default mode.
        self.performSelectorOnMainThread_withObject_waitUntilDone_modes_(
            "drainStates:", None, False, [NSRunLoopCommonModes]
        )

    def drainStates_(self, _):  # noqa: N802 (runs on main thread)
        while True:
            with self._pending_lock:
                if not self._pending:
                    return
                state, info = self._pending.pop(0)
            self._render_state(state, info)

    @objc.python_method
    def _render_state(self, state, info):
        g = info.get

        if state == "ready":
            self._show_state("ready", "Ready — hold fn (🌐) to dictate")
        elif state == "listening":
            self._show_state("listening", "Listening…")
            if self.overlay is not None:
                self.overlay.show()
        elif state == "transcribing":
            self._show_state("transcribing", f"Transcribing {float(g('duration', 0)):0.1f}s…")
            if self.overlay is not None:
                self.overlay.set_mode("thinking")
        elif state == "result":
            text = str(g("text", ""))
            elapsed = float(g("elapsed", 0))
            self.lastItem.setStringValue_(f"Last: “{_truncate(text)}”  ({elapsed:0.1f}s)")
            self._show_state("ready", "Inserted ✓")
            if self.overlay is not None:
                self.overlay.set_mode("done")  # brief green confirm before it retracts
        elif state == "empty":
            self._show_state("ready", "Nothing recognized")
        elif state == "error":
            self._show_state("error", f"Error: {_truncate(str(g('error', '')))}")
        elif state == "idle":
            self._glyph("ready")  # leave the status line on its last message
            if self.overlay is not None:
                self.overlay.hide()

    @objc.python_method
    def _show_state(self, glyph_key, message):
        self._glyph(glyph_key)
        if self.stateItem is not None:
            self.stateItem.setStringValue_(message)

    @objc.python_method
    def _glyph(self, glyph_key):
        if self.statusItem is None:
            return
        button = self.statusItem.button()
        image = _symbol_image(_SYMBOL.get(glyph_key, "ld.waveform"))
        if image is not None:
            button.setImage_(image)
            button.setTitle_("")  # image-only; no stray text beside the icon
        else:  # SF Symbols unavailable — fall back to the emoji glyph
            button.setImage_(None)
            button.setTitle_(_GLYPH.get(glyph_key, "🎙️"))

    @objc.python_method
    def _alert(self, title, message):
        # Bring the (accessory) app forward first. Without this, an accessory app
        # — no Dock icon, usually not the active app — can open its alert unfocused
        # or behind other windows while runModal blocks the main thread, so the app
        # looks frozen with no visible dialog to dismiss. Activating guarantees the
        # modal is front-most and dismissible.
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.runModal()

    # -- menu actions -------------------------------------------------------
    def openDashboard_(self, _):  # noqa: N802
        from .launch import open_dashboard

        self._close_panel()
        open_dashboard()

    def quitApp_(self, _):  # noqa: N802
        self._close_panel()
        self._terminate()

    def applicationWillTerminate_(self, _notification):  # noqa: N802
        # Backstop for any other termination route (Cmd-Q, logout, the app menu).
        # Idempotent with quitApp_, so running both is harmless.
        self._terminate()

    @objc.python_method
    def _terminate(self):
        """Quit for good — guaranteed prompt, crash-free, and never frozen.

        Pressing Quit used to hang whenever a background worker was wedged: the old
        path waited (unbounded) for every thread pool to drain on the main thread,
        so one stuck paste / audio open froze the menu and the app could neither
        quit nor restart. Now we:
          1. arm a hard deadman that force-exits the process after a short grace no
             matter what is wedged,
          2. tear down best-effort with bounded waits, then
          3. exit via os._exit — which skips the interpreter / native-thread
             teardown (and the concurrent.futures atexit join of any wedged
             worker) that originally crashed *and* hung the app on quit.
        Either the clean path reaches os._exit in a few ms, or the deadman fires —
        but the process always dies promptly.
        """
        if getattr(self, "_terminating", False):
            return
        self._terminating = True
        _arm_deadman(4.0)
        try:
            self._teardown()
        except Exception:
            _log("terminate: teardown failed\n" + _traceback())
        _log("=== Voca exiting ===")
        os._exit(0)

    @objc.python_method
    def _teardown(self):
        """Stop all background activity in dependency order. Runs once."""
        if getattr(self, "_torn_down", False):
            return
        self._torn_down = True
        # 1. Stop the hotkey first: once its tap + watchdog threads are joined no
        #    new press/release can fire into the engine while we wind it down.
        try:
            if self.hotkey is not None:
                self.hotkey.stop()
        except Exception:
            _log("teardown: hotkey stop failed\n" + _traceback())
        # 2. Stop the overlay's render timer and order the panel out (main thread).
        try:
            if self.overlay is not None:
                self.overlay.teardown()
        except Exception:
            _log("teardown: overlay teardown failed\n" + _traceback())
        # 3. Drain the engine's worker pools and close the mic stream last, so no
        #    capture / transcription / paste is mid-flight at exit.
        try:
            self.engine.shutdown()
        except Exception:
            _log("teardown: engine shutdown failed\n" + _traceback())


def _do_warmup(controller):
    """Warm the model off the main thread, then install the fn tap on the main run loop.

    A plain module-level function (not a controller method) so it threads reliably
    under py2app. ``controller.engine`` is a plain Python object; the only ObjC
    touch is performSelectorOnMainThread, which is designed to be called from
    background threads.
    """
    try:
        _log("warming up model…")
        elapsed = controller.engine.warmup()  # emits "ready" -> drainStates_ on main
        _log(f"model ready in {elapsed:0.1f}s")
        # Open the mic stream now (no press can race it — the hotkey isn't installed
        # yet) so the first key-down doesn't pay the cold CoreAudio device-open.
        controller.engine.prewarm_audio()
        controller.performSelectorOnMainThread_withObject_waitUntilDone_(
            "installHotkey:", None, False
        )
    except Exception:
        import traceback
        _log("FATAL in warmup:\n" + traceback.format_exc())


def _truncate(text, limit=48):
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Held for the process lifetime so the OS keeps the lock; never closed explicitly.
_INSTANCE_LOCK = None


def _acquire_single_instance() -> bool:
    """Return True if we got the lock; False if another instance already holds it.

    Two instances would mean two event taps firing on every fn press -> doubled
    audio and doubled text insertion.
    """
    global _INSTANCE_LOCK
    path = os.path.join(tempfile.gettempdir(), "voca.lock")
    _INSTANCE_LOCK = open(path, "w")
    try:
        fcntl.flock(_INSTANCE_LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main() -> int:
    app = NSApplication.sharedApplication()
    # Accessory = menu-bar presence, no Dock icon, no window.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    _log("=== Voca launching ===")
    if not _acquire_single_instance():
        _log("another instance is already running — exiting")
        return 0

    engine = DictationEngine()
    controller = DictationController.alloc().initWithEngine_(engine)
    engine._on_state = controller.onEngineState  # wire engine -> UI

    # Defer all setup to applicationDidFinishLaunching: the app must be fully
    # launched before macOS will present the microphone-permission prompt.
    app.setDelegate_(controller)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
