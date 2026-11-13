#!/usr/bin/env python3
"""
profile-menu.py — a minimal terminal menu for your command shortcuts.

Navigate with Up/Down (or j/k), jump straight to an item with its hotkey
(if it has one), press Enter to run, q or Esc to quit.

CUSTOMIZE: shortcuts live in items.py (in the same directory as this
script), not here. Edit that file's ITEMS list — this script's logic
stays untouched. See items.py for the entry format.

The script clears the screen, shows the menu, then on selection it exits
curses mode and actually runs the command in your normal terminal (so
interactive commands like `htop`, `ssh`, `vim` etc. work fine).

Supported shells: bash, zsh, fish. See _shell_invocation() for details.
"""

import curses
import os
import subprocess
import sys

# items.py must sit next to this script for the import below to find it,
# regardless of the directory this script is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from items import ITEMS  # noqa: E402  (must come after the sys.path tweak)

# ─────────────────────────────────────────────────────────────
# EDIT THIS MAP — colors used by the UI.
# Values are curses color names: BLACK, RED, GREEN, YELLOW, BLUE,
# MAGENTA, CYAN, WHITE, or -1 for the terminal's own default color.
# "fg"/"bg" = foreground/background.
#
# Note: the selected row isn't listed here — it's drawn with reverse
# video (swap fg/bg) instead of a fixed color, so it stays high
# contrast regardless of your terminal's color theme/palette.
# ─────────────────────────────────────────────────────────────
COLOR_MAP = {
    "normal":       {"fg": -1, "bg": -1},  # unselected rows (terminal default)
    "instructions": {"fg": -1, "bg": -1},  # help text at bottom
}

MARGIN = 2  # spaces of padding on both the left and right edges of the menu


def _resolve_color(name):
    """Translate a color name string (or -1) from COLOR_MAP into a curses constant."""
    if name == -1:
        return -1
    return getattr(curses, f"COLOR_{name.upper()}")


def _init_colors():
    """Build curses color pairs from COLOR_MAP. Returns a name -> pair-number dict."""
    curses.start_color()
    curses.use_default_colors()
    pairs = {}
    for i, (role, spec) in enumerate(COLOR_MAP.items(), start=1):
        curses.init_pair(i, _resolve_color(spec["fg"]), _resolve_color(spec["bg"]))
        pairs[role] = curses.color_pair(i)
    return pairs


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


GAP = "  "  # fixed space kept between the command and the label/hotkey block
START_Y = 1  # row where the item list begins


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


def draw_menu(stdscr, selected_idx):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    curses.curs_set(0)
    colors = _init_colors()

    start_x = MARGIN
    start_y = START_Y
    line_w = max(width - (MARGIN * 2), 0)  # usable columns per row (equal margins)
    hotkey_field_w = _hotkey_field_width()

    for idx, item in enumerate(ITEMS):
        row = start_y + idx
        if row >= height - 2:
            continue
        text = _build_row(
            item["command"], item.get("label"), item.get("hotkey"),
            line_w, hotkey_field_w,
        )

        if idx == selected_idx:
            stdscr.attron(colors["normal"] | curses.A_REVERSE | curses.A_BOLD)
            padded = text + " " * max(line_w - len(text), 0)
            stdscr.addstr(row, start_x, padded[:line_w])
            stdscr.attroff(colors["normal"] | curses.A_REVERSE | curses.A_BOLD)
        else:
            stdscr.attron(colors["normal"])
            stdscr.addstr(row, start_x, text[:line_w])
            stdscr.attroff(colors["normal"])

    # Instructions
    help_text = "up/down or j/k: move   enter: run   letter: jump+run   q: quit"
    footer_row = start_y + len(ITEMS) + 1
    if footer_row < height:
        stdscr.attron(colors["instructions"])
        stdscr.addstr(footer_row, start_x, help_text[:line_w])
        stdscr.attroff(colors["instructions"])

    stdscr.refresh()


def run_menu(stdscr):
    curses.curs_set(0)
    selected_idx = 0

    # Only items with a real hotkey get registered for jump+run
    hotkeys = {
        item["hotkey"].lower(): i for i, item in enumerate(ITEMS) if item.get("hotkey")
    }

    while True:
        draw_menu(stdscr, selected_idx)
        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):  # move selection up
            selected_idx = (selected_idx - 1) % len(ITEMS)
        elif key in (curses.KEY_DOWN, ord('j')):  # move selection down
            selected_idx = (selected_idx + 1) % len(ITEMS)
        elif key in (curses.KEY_ENTER, 10, 13):  # run the highlighted item
            return ITEMS[selected_idx]
        elif key in (ord('q'), ord('Q'), 27):  # q or Esc (27) cancels
            return None
        else:
            # any other key: check if it matches an item's hotkey
            try:
                ch = chr(key).lower()
            except ValueError:
                continue
            if ch in hotkeys:
                return ITEMS[hotkeys[ch]]


def main():
    try:
        item = curses.wrapper(run_menu)
    except curses.error as e:
        print(f"Terminal too small or unsupported: {e}", file=sys.stderr)
        sys.exit(1)

    if item is None:
        print("Cancelled.")
        return

    command = item["command"]
    cd = item.get("cd")  # optional per-item working directory
    cwd = os.path.expanduser(cd) if cd else None
    if cwd and not os.path.isdir(cwd):
        print(f"cd target not found: {cd}", file=sys.stderr)
        sys.exit(1)

    # curses.wrapper() restores normal terminal modes on exit, but some
    # terminals still leave stray color/attribute state (e.g. reverse
    # video) bleeding into the screen buffer. That can show up as visual
    # garbling once a full-screen program (vim, nano, htop...) takes over
    # its own alternate screen and later hands control back. An explicit
    # SGR reset + clear avoids that.
    sys.stdout.write("\033[0m\033[2J\033[H")
    sys.stdout.flush()

    print(f"\n$ {f'cd {cd} && ' if cd else ''}{command}\n")

    user_shell = os.environ.get("SHELL", "/bin/bash")
    # cwd= applies the directory to this command only, like `cd foo` in a
    # subshell; the menu's own working directory is left alone.
    subprocess.run(_shell_invocation(user_shell, command), cwd=cwd)


if __name__ == "__main__":
    main()
