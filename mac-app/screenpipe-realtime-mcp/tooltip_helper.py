#!/usr/bin/env python3
"""Native macOS floating tooltip near the cursor.

Usage:
    python tooltip_helper.py "Message" 5

Displays a rounded rectangle with translucent background near the current
cursor location, auto-closes after N seconds.  Requires `pyobjc`.
"""
from __future__ import annotations
import sys
import Cocoa

# Compatibility: Style masks changed naming after macOS 10.12 / PyObjC 5
if hasattr(Cocoa, "NSWindowStyleMaskBorderless"):
    BORDERLESS = Cocoa.NSWindowStyleMaskBorderless  # modern constant
    BACKING    = Cocoa.NSBackingStoreBuffered
else:
    BORDERLESS = Cocoa.NSBorderlessWindowMask       # legacy constant
    BACKING    = Cocoa.NSBackingStoreBuffered

TEXT = sys.argv[1] if len(sys.argv) > 1 else "Hello Tooltip"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 4
PADDING = 12

# Cursor position (Quartz origin bottom-left) → Cocoa origin top-left
loc = Cocoa.NSEvent.mouseLocation()
screen_height = Cocoa.NSScreen.mainScreen().frame().size.height
x, y = int(loc.x), int(screen_height - loc.y)

# Create window using compatible style mask
win = Cocoa.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    Cocoa.NSMakeRect(x, y, 10, 10), BORDERLESS, BACKING, False
)
win.setLevel_(Cocoa.NSStatusWindowLevel + 3)
win.setOpaque_(False)
win.setBackgroundColor_(Cocoa.NSColor.clearColor())
win.setIgnoresMouseEvents_(True)

# Text field
field = Cocoa.NSTextField.alloc().initWithFrame_(Cocoa.NSMakeRect(0, 0, 10, 10))
field.setStringValue_(TEXT[:200])
field.setBezeled_(False)
field.setBordered_(False)
field.setEditable_(False)
field.setSelectable_(False)
field.setBackgroundColor_(Cocoa.NSColor.clearColor())
field.sizeToFit()

w, h = field.frame().size
w += PADDING * 2
h += PADDING * 2
field.setFrameOrigin_((PADDING, PADDING))

# Reposition window so it is centered horizontally and 16 px above cursor
new_x = x - w / 2
new_y = y - h - 16
win.setFrame_display_(Cocoa.NSMakeRect(new_x, new_y, w, h), True)

# Container view with rounded rectangle background (no quartzPath)
view = Cocoa.NSView.alloc().initWithFrame_(Cocoa.NSMakeRect(0, 0, w, h))
view.setWantsLayer_(True)
layer = view.layer()
layer.setBackgroundColor_(
    Cocoa.NSColor.windowBackgroundColor().colorWithAlphaComponent_(0.95).CGColor()
)
layer.setCornerRadius_(8.0)
view.addSubview_(field)

win.setContentSize_((w, h))
win.setContentView_(view)
win.orderFrontRegardless()

# Close after DURATION seconds
Cocoa.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    DURATION, win, "close", None, False
)

# Fade-out: gradually reduce alpha over 0.4 s before closing
STEP = 0.05
fade_start = max(DURATION - 0.4, 0)

def fade_tick(timer):
    alpha = win.alphaValue() - STEP
    if alpha <= 0:
        win.close()
        Cocoa.NSTimer.cancelPreviousPerformRequestsWithTarget_(fade_tick)
    else:
        win.setAlphaValue_(alpha)

Cocoa.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    fade_start, win, "setAlphaValue_", None, False
)
Cocoa.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    0.05, None, "fade_tick:", None, True
)

def finish(_: object | None = None):
    Cocoa.NSApp.stop_(None)

# timer that closes window already exists – attach finish afterwards
def close_and_quit(timer):
    win.close()
    finish()

# replace the previous close timer line with:
Cocoa.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    DURATION, None, "close_and_quit:", None, False
)

Cocoa.NSApp.run() 