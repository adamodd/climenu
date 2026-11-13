#!/usr/bin/env python3
"""
profile-menu.py — a minimal terminal menu for your command shortcuts.

The menu draws inline, just below your prompt (like fzf's Ctrl-R), instead
of taking over the whole screen. It redraws in place and never clears the
screen, so none of its frames end up in your terminal's scrollback, and it
erases itself when you're done.

    Up/Down     move the highlight (the mouse wheel does too)
    Enter       run the highlighted item
    click       run the clicked item
    hotkey      jump to and run that item, if it has one
    q or Esc    quit without running anything

CUSTOMIZE: shortcuts live in items.py (in the same directory as this
script), not here. Edit that file's ITEMS list — this script's logic
stays untouched. See items.py for the entry format.

On selection the menu erases itself, then runs the command in your normal
terminal (so interactive commands like `htop`, `ssh`, `vim` etc. work fine).

Exit status: 0 if a command ran, 130 if you quit without running one.
The shell hotkey snippets in readme.md use this to know whether to redraw
the prompt in place (nothing ran) or below the command's output.

Uses only the Python standard library. Needs a Unix terminal (macOS, Linux).
Supported shells: bash, zsh, fish. See _shell_invocation() for details.
"""

import os
import re
import select
import signal
import subprocess
import sys
import termios
import tty
from collections import namedtuple

# items.py must sit next to this script for the import below to find it,
# regardless of the directory this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from items import ITEMS  # noqa: E402  (must come after the sys.path tweak)

# ─────────────────────────────────────────────────────────────
# EDIT THIS MAP — colors used by the UI.
# Values are color names: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA,
# CYAN, WHITE, or -1 for the terminal's own default color.
# "fg"/"bg" = foreground/background.
#
# Note: the selected row isn't listed here — it's drawn with reverse
# video (swap fg/bg) instead of a fixed color, so it stays high
# contrast regardless of your terminal's color theme/palette.
# ─────────────────────────────────────────────────────────────
COLOR_MAP = {
    "normal": {"fg": -1, "bg": -1},  # menu rows (terminal default)
}

MARGIN = 2  # spaces of padding on both the left and right edges of the menu
GAP = "  "  # fixed space kept between the command and the label/hotkey block

_COLOR_NAMES = ["BLACK", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE"]


def _style(role, selected=False):
    """ANSI code that switches on a COLOR_MAP role's colors (plus bold +
    reverse video for the selected row)."""
    spec = COLOR_MAP[role]
    fg = 39 if spec["fg"] == -1 else 30 + _COLOR_NAMES.index(spec["fg"].upper())
    bg = 49 if spec["bg"] == -1 else 40 + _COLOR_NAMES.index(spec["bg"].upper())
    return f"\033[0;{fg};{bg}{';1;7' if selected else ''}m"


def _shell_invocation(user_shell, command):
    """
    Build the subprocess argv that runs `command` the way the user's own
    shell normally would — i.e. with their aliases/functions/env available —
    without hardcoding any specific rc filename, and without invoking a
    full interactive shell.

    Supported shells: bash, zsh, fish (the common cases). Other POSIX-ish
    shells (ksh, dash, tcsh...) aren't explicitly tested; dash in particular
    doesn't support aliases the same way and may behave differently.

    This is the same idea as `su -` vs `su`: instead of manually replicating
    a shell's startup sequence (sourcing one guessed file), we ask the shell
    itself to run its own normal startup chain by requesting a login (-l)
    shell, which sources the profile/login files where aliases are usually
    defined.

    NOTE: this deliberately does NOT use -i (interactive mode). -i would
    also enable bash alias expansion, but it also turns on job control,
    which can fail with "no job control" errors when the shell is invoked
    a few subprocess layers deep (e.g. iTerm2 -> this script -> the
    command's shell) rather than as a real top-level session shell.
    Instead, bash gets alias expansion turned on directly via
    `shopt -s expand_aliases`, and zsh already expands aliases in
    non-interactive shells by default — so neither needs -i.
    """
    shell_name = os.path.basename(user_shell)

    if shell_name == "fish":
        # fish always loads ~/.config/fish/config.fish for every shell type,
        # login or not, interactive or not — no flags needed to get there.
        return [user_shell, "-c", command]

    if shell_name == "bash":
        # bash disables alias expansion in non-interactive shells unless
        # explicitly turned back on with this shopt — no need for -i.
        # IMPORTANT: this must be joined with a newline, not `;`. bash
        # parses a `;`-joined -c string as one lookahead unit, so the
        # shopt doesn't take effect in time for an alias used later on
        # the same logical line — a real newline forces a separate parse
        # step, which is what actually makes the alias resolve.
        wrapped = f"shopt -s expand_aliases 2>/dev/null\n{command}"
        return [user_shell, "-l", "-c", wrapped]

    # zsh (and likely other bash-like shells): aliases already expand in
    # non-interactive shells, so a plain login shell is enough.
    return [user_shell, "-l", "-c", command]


# ─────────────────────────────────────────────────────────────
# Row layout
# ─────────────────────────────────────────────────────────────

def _truncate(text, max_w):
    """Shorten text to fit max_w columns, adding an ellipsis if it was cut."""
    if max_w <= 0:
        return ""
    if len(text) <= max_w:
        return text
    if max_w == 1:
        return "…"
    return text[: max_w - 1] + "…"


def _hotkey_field_width():
    """Width of the [x] hotkey field, fixed across all rows (even empty ones)
    so the label column's right edge lines up on every row."""
    hotkey_w = max([len(i["hotkey"]) for i in ITEMS if i.get("hotkey")] + [1])
    return hotkey_w + 2  # + 2 for the surrounding brackets


def _build_row(command, label, hotkey, line_w, hotkey_field_w):
    """
    Right-float layout (not a fixed table): the label/hotkey block sits
    flush against the right edge. The hotkey field is a fixed width on
    every row (blank when there's no hotkey), so the label's right edge
    lines up consistently row to row. The command is the flexible part —
    it fills whatever space is left before that block and truncates
    (with an ellipsis) if needed.
    """
    hk_field = f"{f'[{hotkey}]' if hotkey else '':>{hotkey_field_w}}"
    right_block = f"{label}{GAP}{hk_field}" if label else hk_field

    command_w = max(line_w - len(right_block) - len(GAP), 4)
    command_display = _truncate(command, command_w)

    return f"{command_display:<{command_w}}{GAP}{right_block}"


# ─────────────────────────────────────────────────────────────
# Terminal control codes. The menu is drawn with nothing but these:
# move the cursor, write a row, erase to the end of the row or screen.
# There is deliberately no "clear screen": iTerm2 and Terminal.app
# copy the screen into scrollback when it's cleared, which is what
# filled scrollback with menu frames in the old curses version.
# ─────────────────────────────────────────────────────────────
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
MOUSE_ON = "\033[?1000h\033[?1006h"   # report clicks and wheel (1006 = modern format)
MOUSE_OFF = "\033[?1006l\033[?1000l"
ERASE_TO_EOL = "\033[K"               # erase from the cursor to the end of the line
ERASE_BELOW = "\033[J"                # erase from the cursor to the end of the screen
RESET_STYLE = "\033[0m"
ASK_CURSOR = "\033[6n"                # terminal replies "ESC [ row ; col R"


def _up(n):
    return f"\033[{n}A" if n else ""  # (a count of 0 would still move 1 line)


def _column(col):
    return f"\033[{col}G"


# Input arrives as raw bytes. Keys like Up send several bytes starting
# with ESC; mouse clicks do too. These patterns pick them apart.
_SGR_MOUSE = re.compile(rb"\033\[<(\d+);(\d+);(\d+)([Mm])")    # mouse, modern format
_X10_MOUSE = re.compile(rb"\033\[M([\s\S])([\s\S])([\s\S])")   # mouse, older format
_ARROW = re.compile(rb"\033[\[O]([AB])")   # Up/Down ("O" form if the shell enabled keypad mode)
_OTHER_KEY = re.compile(rb"\033(\[[0-?]*[ -/]*[@-~]|O[\s\S])")  # any other special key: ignored
_UNFINISHED = re.compile(rb"\033(\[[0-?]*[ -/]*|\[M[\s\S]{0,2}|O)?\Z")  # start of one of the above


def _mouse_event(button, row, released):
    """Turn a mouse report into a menu event (see _decode)."""
    button &= ~(4 | 8 | 16)  # ignore Shift/Alt/Ctrl held during the click
    if button == 64:
        return ("up", None)  # wheel up
    if button == 65:
        return ("down", None)  # wheel down
    if button in (0, 3):  # left button (the older format reports any release as 3)
        return ("release" if released else "press", row)
    return None


def _decode(buf):
    """
    Take one input event off the front of buf. Returns (event, rest_of_buf).
    An event is a (kind, value) pair:
        ("up", None) ("down", None) ("enter", None) ("quit", None)
        ("key", "x")                     a plain key press
        ("press", row) ("release", row)  left mouse button, at that screen row
    or None for input the menu doesn't use.
    """
    first = buf[:1]
    if first in (b"\r", b"\n"):
        return ("enter", None), buf[1:]
    if first == b"\x03":  # Ctrl-C (in raw mode it arrives as an ordinary key)
        return ("quit", None), buf[1:]
    if first != b"\033":
        return ("key", first.decode("latin-1")), buf[1:]

    m = _SGR_MOUSE.match(buf)
    if m:
        return _mouse_event(int(m[1]), int(m[3]), released=m[4] == b"m"), buf[m.end():]
    m = _X10_MOUSE.match(buf)
    if m:
        button = m[1][0] - 32
        return _mouse_event(button, m[3][0] - 32, released=button & 3 == 3), buf[m.end():]
    m = _ARROW.match(buf)
    if m:
        return ("up" if m[1] == b"A" else "down", None), buf[m.end():]
    m = _OTHER_KEY.match(buf)
    if m:
        return None, buf[m.end():]
    return ("quit", None), buf[1:]  # a lone ESC: the Esc key


class Terminal:
    """
    The controlling terminal (/dev/tty), switched to raw mode: each key
    arrives as soon as it's pressed, without being echoed, and output is
    sent exactly as written. (So "\\n" moves straight down without going
    back to column 1, which Menu._make_room relies on.)

    Talking to /dev/tty directly, rather than stdin/stdout, keeps the menu
    working even if the script's input or output is redirected.
    """

    def __init__(self):
        self.fd = os.open("/dev/tty", os.O_RDWR)
        self.shell_mode = termios.tcgetattr(self.fd)  # the mode the shell left it in
        tty.setraw(self.fd, termios.TCSANOW)
        self.pending = b""  # input read but not decoded into an event yet

    def restore_shell_mode(self):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.shell_mode)

    def set_line_mode(self):
        """
        The terminal's normal mode for running a command: typed keys are
        echoed, Enter submits a line, Ctrl-C interrupts. When launched by
        bash's Ctrl-G binding, the shell mode is still the line editor's own
        (no echo), so a command that asks a question, like apt's "Continue?
        [Y/n]", wouldn't show what you type without this.
        """
        mode = termios.tcgetattr(self.fd)
        mode[0] |= termios.ICRNL  # Enter key sends a newline
        mode[1] |= termios.OPOST | termios.ONLCR  # "\n" also returns to column 1
        mode[3] |= (termios.ICANON | termios.ECHO | termios.ECHOE | termios.ECHOK
                    | termios.ISIG | termios.IEXTEN)
        termios.tcsetattr(self.fd, termios.TCSADRAIN, mode)

    def write(self, text):
        data = text.encode()
        while data:
            data = data[os.write(self.fd, data):]

    def size(self):
        return os.get_terminal_size(self.fd)

    def _fill(self, timeout):
        """Wait up to `timeout` seconds for input and add it to self.pending.
        Returns whether anything arrived."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if ready:
            self.pending += os.read(self.fd, 1024)
        return bool(ready)

    def cursor_position(self):
        """Ask the terminal where the cursor is: (row, col), counting from 1.
        Returns None if the terminal doesn't answer."""
        self.write(ASK_CURSOR)
        while True:
            m = re.search(rb"\033\[(\d+);(\d+)R", self.pending)
            if m:
                # keep any keys typed while we waited for the answer
                self.pending = self.pending[:m.start()] + self.pending[m.end():]
                return int(m[1]), int(m[2])
            if not self._fill(0.5):
                return None

    def read_event(self, timeout):
        """Next input event (see _decode), or None if nothing usable
        arrived within `timeout` seconds."""
        if not self.pending and not self._fill(timeout):
            return None
        # The Esc key sends a lone ESC byte, but ESC also starts the byte
        # sequences of arrow keys and mouse clicks. If what we have could
        # be the start of a sequence, give the rest a moment to arrive.
        if _UNFINISHED.match(self.pending):
            self._fill(0.05)
        event, self.pending = _decode(self.pending)
        return event


# Where the menu sits on screen:
#   size      terminal size it was laid out for
#   rows      how many menu rows fit (the list scrolls if there are more items)
#   row, col  the "anchor": where the shell left the cursor. The cursor rests
#             here between redraws. row is None if the terminal didn't
#             report it; mouse clicks are ignored then.
#   lead      0 if the menu's first row is on the anchor line itself (the
#             cursor was at the start of an empty line), 1 if it starts on
#             the line below (the cursor was on the prompt line, after it).
Layout = namedtuple("Layout", "size rows row col lead")


class Menu:
    def __init__(self, term):
        self.term = term
        self.layout = None
        self.selected = 0
        self.top = 0  # index of the first item shown
        # Only items with a real hotkey get registered for jump+run
        self.hotkeys = {
            item["hotkey"].lower(): i for i, item in enumerate(ITEMS) if item.get("hotkey")
        }

    def run(self):
        """Show the menu until something is chosen. Returns the item, or None."""
        pressed = None  # item the mouse button went down on
        redraw = True
        while True:
            if self.layout is None or self.term.size() != self.layout.size:
                self._make_room()
                redraw = True
            if redraw:
                self._draw()
                redraw = False

            # The timeout wakes the loop regularly so it notices resizes.
            event = self.term.read_event(timeout=0.1)
            if event is None:
                continue
            redraw = True
            kind, value = event

            if kind == "up":
                self.selected = (self.selected - 1) % len(ITEMS)
            elif kind == "down":
                self.selected = (self.selected + 1) % len(ITEMS)
            elif kind == "enter":
                return ITEMS[self.selected]
            elif kind == "quit":
                return None
            elif kind == "key":
                if value in ("q", "Q"):
                    return None
                if value.lower() in self.hotkeys:
                    return ITEMS[self.hotkeys[value.lower()]]
            elif kind == "press":
                # Highlight on press, run on release, like a normal button.
                # Acting on press would leave the release report unread, and
                # the shell would then see it as typed text.
                pressed = self._item_at(value)
                if pressed is not None:
                    self.selected = pressed
            elif kind == "release":
                if pressed is not None and self._item_at(value) == pressed:
                    return ITEMS[pressed]
                pressed = None

    def close(self, running):
        """Erase the menu. Leaves the cursor on the anchor, or, if a command
        is about to run, at the start of an empty line for its output."""
        if self.layout is None:
            return
        lead = self.layout.lead
        out = ("\r\n" if lead else "\r") + ERASE_BELOW  # erase from the menu's first line down
        if not (running and lead):
            # Back to the anchor. (When running with lead=1 the cursor stays
            # put instead: the anchor line has the prompt on it, so the
            # command's output starts on the empty line below.)
            out += _up(lead) + _column(self.layout.col)
        self.term.write(out)

    def _make_room(self):
        """
        Work out where the menu goes, and make sure there's room for it.

        Printing newlines makes the terminal scroll up if the anchor is near
        the bottom, so the menu always fits; then the cursor goes back up to
        the anchor. Runs at startup and after every resize, since the
        terminal may have rewrapped or scrolled lines.
        """
        size = self.term.size()
        row, col = self.term.cursor_position() or (None, 1)
        # At the start of an empty line (a fresh line, or one the shell
        # cleared), the menu starts right there. Otherwise the cursor is on
        # the prompt line, and the menu starts below so the prompt stays.
        lead = 0 if col == 1 else 1
        rows = max(min(len(ITEMS), size.lines - lead), 1)
        below = rows - 1 + lead  # lines the menu needs below the anchor
        self.term.write("\n" * below + _up(below))
        if row is not None:
            row = min(row, size.lines - below)  # where the anchor is after any scrolling
        self.layout = Layout(size, rows, row, min(col, size.columns), lead)

    def _item_at(self, screen_row):
        """Index of the item drawn on that screen row, or None."""
        if self.layout.row is None:
            return None
        offset = screen_row - self.layout.row - self.layout.lead
        if 0 <= offset < self.layout.rows:
            return self.top + offset
        return None

    def _draw(self):
        """Redraw every menu row in place, then rest the cursor on the anchor."""
        rows, width = self.layout.rows, self.layout.size.columns

        # Scroll the visible window of rows so the selection is in it.
        self.top = min(self.top, self.selected)
        self.top = max(self.top, self.selected - rows + 1)
        self.top = min(self.top, len(ITEMS) - rows)

        # Usable columns per row. The right margin is at least 1 even if
        # MARGIN is 0: writing in the last column leaves the terminal
        # waiting to wrap, and the row rewraps badly on resize.
        line_w = max(width - MARGIN - max(MARGIN, 1), 0)
        hotkey_field_w = _hotkey_field_width()

        lines = []
        for idx in range(self.top, self.top + rows):
            item = ITEMS[idx]
            text = _build_row(
                item["command"], item.get("label"), item.get("hotkey"),
                line_w, hotkey_field_w,
            )
            if idx == self.selected:
                text = _style("normal", selected=True) + f"{text:<{line_w}}"[:line_w]
            else:
                text = _style("normal") + text[:line_w]
            # The row, then erase whatever the previous frame left past its end.
            lines.append(" " * MARGIN + text + RESET_STYLE + ERASE_TO_EOL)

        lead = self.layout.lead
        self.term.write(
            ("\r\n" if lead else "\r")  # start of the menu's first line
            + "\r\n".join(lines)        # "\r\n" = start of the next line down
            + ERASE_BELOW               # leftovers below, e.g. lines rewrapped by a resize
            + _up(rows - 1 + lead) + _column(self.layout.col)  # back to the anchor
        )


def main():
    if not ITEMS:
        print("profile-menu: items.py has no ITEMS to show", file=sys.stderr)
        sys.exit(1)
    try:
        term = Terminal()
    except (OSError, termios.error) as e:
        print(f"profile-menu: needs an interactive terminal ({e})", file=sys.stderr)
        sys.exit(1)

    menu = Menu(term)
    item = None
    try:
        term.write(HIDE_CURSOR + MOUSE_ON)
        item = menu.run()
    finally:
        # Runs even if something above crashes, so the terminal is never
        # left in raw mode with the cursor hidden.
        menu.close(running=item is not None)
        term.write(MOUSE_OFF + SHOW_CURSOR)
        term.restore_shell_mode()

    if item is None:
        sys.exit(130)  # tells the shell snippets nothing was printed

    command = item["command"]
    cd = item.get("cd")  # optional per-item working directory
    cwd = os.path.expanduser(cd) if cd else None
    if cwd and not os.path.isdir(cwd):
        print(f"cd target not found: {cd}", file=sys.stderr)
        sys.exit(1)

    term.set_line_mode()
    print(f"$ {f'cd {cd} && ' if cd else ''}{command}", flush=True)

    # Ctrl-C while the command runs is meant for the command. Python would
    # also get it and print a traceback, so give it a do-nothing handler.
    # (A handler, not SIG_IGN: the command must not inherit "ignore Ctrl-C".)
    signal.signal(signal.SIGINT, lambda *_: None)

    user_shell = os.environ.get("SHELL", "/bin/bash")
    try:
        # cwd= applies the directory to this command only, like `cd foo` in
        # a subshell; the menu's own working directory is left alone.
        result = subprocess.run(_shell_invocation(user_shell, command), cwd=cwd)
        if result.returncode in (-signal.SIGINT, 128 + signal.SIGINT):
            print()  # stopped with Ctrl-C: end the "^C" line so the prompt gets its own
    finally:
        term.restore_shell_mode()


if __name__ == "__main__":
    main()
