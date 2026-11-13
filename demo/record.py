#!/usr/bin/env python3
"""
record.py — records the animated demo at the top of readme.md.

Runs the real climenu and para inside a real zsh, in a pseudo-terminal,
presses keys on a script (SCENE below), captures every screen frame with
pyte (a terminal emulator library), and writes demo/climenu-demo.svg: an
animated SVG that GitHub plays inline. Nothing is faked except the demo
project's commands (a git repo and two pretend dev servers).

    pip install pyte        # only needed for this script
    python3 demo/record.py

Re-run it whenever the menu's look or behaviour changes.
"""

import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
from html import escape

import pyte

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "demo", "climenu-demo.svg")
COLS, LINES = 74, 16

# The demo menu. Only "Git status" and "Start dev servers" are run.
DEMO_COMMANDS = """COMMANDS = [
    {"command": "git status", "label": "Git status", "hotkey": "g", "cd": "~/code/shop"},
    {"command": "para -t ./web ./api", "label": "Start dev servers", "hotkey": "s", "cd": "~/code/shop"},
    {"command": "make test", "label": "Run tests", "hotkey": "t", "cd": "~/code/shop"},
    {"command": "ssh pi@homelab", "label": "SSH to homelab", "hotkey": "h"},
    {"command": "brew upgrade", "label": "Update packages", "hotkey": "u"},
]
"""

# A pretend dev server: prints a log line now and then; says goodbye on Ctrl-C.
FAKE_SERVER = """#!/bin/sh
trap 'echo "shutting down"; exit 0' TERM
echo "listening on :$1"
for path in $2; do sleep $3; echo "GET $path 200"; done
while :; do sleep 1; done
"""

# The demo, as (keys to press, caption shown for them, seconds to wait after).
CTRL_G, DOWN, UP, ENTER, CTRL_C = "\x07", "\033[B", "\033[A", "\r", "\x03"
SCENE = [
    (None, None, 1.2),
    (CTRL_G, "Ctrl-G", 1.0),
    (DOWN, "↓", 0.5), (DOWN, "↓", 0.5), (UP, "↑", 0.9),
    ("q", "q  (closes, leaves no trace)", 1.6),
    (CTRL_G, "Ctrl-G", 0.9),
    ("g", "g  (hotkey)", 2.2),
    (CTRL_G, "Ctrl-G", 0.8),
    (DOWN, "↓", 0.8),
    (ENTER, "Enter", 3.4),
    (CTRL_C, "Ctrl-C  (stops both)", 2.4),
]


def make_demo_home():
    """A throwaway home folder: zsh config with the readme's hotkey snippet,
    the installed scripts, and a small git project with two fake servers."""
    home = tempfile.mkdtemp(prefix="climenu-demo-")
    scripts = os.path.join(home, "scripts")
    os.makedirs(scripts)
    for name in ("climenu.py", "para"):
        shutil.copy(os.path.join(REPO, name), scripts)
    with open(os.path.join(scripts, "clicommands.py"), "w") as f:
        f.write(DEMO_COMMANDS)

    with open(os.path.join(REPO, "readme.md")) as f:
        readme = f.read()
    widget = readme.split("```zsh\n", 1)[1].split("```", 1)[0]
    with open(os.path.join(home, ".zshrc"), "w") as f:
        f.write("PROMPT='%F{cyan}~/code/shop%f %% '\n")
        f.write(f"path=({scripts} $path)\n")
        f.write(widget.replace("~/scripts", scripts))

    shop = os.path.join(home, "code", "shop")
    os.makedirs(shop)
    for name, port, paths, delay in (("web", 3000, "/ /cart /checkout", 0.7),
                                     ("api", 8080, "/items /items/42", 0.9)):
        path = os.path.join(shop, name)
        with open(path, "w") as f:
            f.write(FAKE_SERVER.replace("$1", str(port)).replace("$2", paths).replace("$3", str(delay)))
        os.chmod(path, 0o755)
    git = ["git", "-C", shop, "-c", "user.name=demo", "-c", "user.email=demo@example.com"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "main"], check=True)
    with open(os.path.join(shop, "cart.js"), "w") as f:
        f.write("// cart\n")
    subprocess.run(git + ["add", "web", "api"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "servers"], check=True)
    with open(os.path.join(shop, "web"), "a") as f:
        f.write("# tweak\n")
    return home


def record(home):
    """Run the scene. Returns a list of (seconds, screen snapshot, caption)."""
    pid, fd = pty.fork()
    if pid == 0:
        env = {"HOME": home, "ZDOTDIR": home, "TERM": "xterm-256color", "SHELL": "/bin/zsh",
               "PATH": os.environ["PATH"], "LANG": "C.UTF-8"}
        os.execve("/bin/zsh", ["zsh", "-i"], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", LINES, COLS, 0, 0))

    class Screen(pyte.Screen):
        def write_process_input(self, data):  # answer cursor-position queries
            os.write(fd, data.encode())

    screen = Screen(COLS, LINES)
    stream = pyte.ByteStream(screen)
    frames = []
    caption = None
    last = time.time()

    def pump(seconds):
        nonlocal last
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.04)
            if ready:
                stream.feed(os.read(fd, 65536))
            snap = snapshot(screen)
            if frames and frames[-1][1] == snap and frames[-1][2] == caption:
                continue
            now = time.time()
            if frames:
                frames[-1][0] = now - last
            frames.append([0.0, snap, caption])
            last = now

    pump(1.5)                    # let zsh start
    frames.clear()
    last = time.time()
    for keys, label, wait in SCENE:
        caption = label
        if keys:
            os.write(fd, keys.encode())
        pump(wait)
    frames[-1][0] = time.time() - last + 1.0
    os.kill(pid, signal.SIGKILL)
    return frames


def snapshot(screen):
    """The visible screen as rows of (text, fg, bold, reverse) runs, plus the cursor."""
    rows = []
    for y in range(screen.lines):
        line, runs = screen.buffer[y], []
        for x in range(screen.columns):
            ch = line[x]
            style = (ch.fg, ch.bold, ch.reverse)
            if runs and tuple(runs[-1][1:]) == style:
                runs[-1][0] += ch.data
            else:
                runs.append([ch.data, *style])
        rows.append(tuple(tuple(r) for r in runs))
    cursor = None if screen.cursor.hidden else (screen.cursor.x, screen.cursor.y)
    return tuple(rows), cursor


# ─── SVG output ───────────────────────────────────────────────
CW, LH, FS = 8.4, 19, 14          # character width, line height, font size (px)
PAD, BAR, CAP = 14, 30, 30        # padding, title bar, caption strip
BG, FG = "#1e1e2e", "#cdd6f4"
COLORS = {"default": FG, "cyan": "#89dceb", "green": "#a6e3a1", "red": "#f38ba8",
          "yellow": "#f9e2af", "blue": "#89b4fa", "magenta": "#cba6f7", "white": "#ffffff"}


def frame_svg(snap, caption):
    rows, cursor = snap
    out = []
    for y, runs in enumerate(rows):
        x, base = 0, PAD + BAR + y * LH
        for text, fg, bold, reverse in runs:
            width = len(text) * CW
            color = COLORS.get(fg, FG)
            if reverse:
                out.append(f'<rect x="{PAD + x * CW:.1f}" y="{base:.1f}" width="{width:.1f}" height="{LH}" fill="{color}"/>')
                color = BG
            # Draw only the visible part, at its exact column. textLength pins
            # its width to the grid whatever monospace font the viewer has.
            shown = text.strip()
            if shown:
                left = x + len(text) - len(text.lstrip())
                weight = ' font-weight="bold"' if bold else ""
                out.append(f'<text x="{PAD + left * CW:.1f}" y="{base + LH * 0.75:.1f}" fill="{color}"{weight} '
                           f'textLength="{len(shown) * CW:.1f}" lengthAdjust="spacingAndGlyphs">{escape(shown)}</text>')
            x += len(text)
    if cursor:
        cx, cy = cursor
        out.append(f'<rect x="{PAD + cx * CW:.1f}" y="{PAD + BAR + cy * LH:.1f}" width="{CW}" height="{LH}" fill="{FG}" opacity="0.7"/>')
    if caption:
        out.append(f'<text class="cap" x="{PAD}" y="{PAD + BAR + LINES * LH + CAP * 0.7:.1f}">{escape(caption)}</text>')
    return "".join(out)


def write_svg(frames):
    total = sum(d for d, _, _ in frames)
    width = PAD * 2 + COLS * CW
    height = PAD * 2 + BAR + LINES * LH + CAP
    css, groups, t = [], [], 0.0
    for i, (duration, snap, caption) in enumerate(frames):
        start, end = t / total * 100, (t + duration) / total * 100
        t += duration
        keys = (f"0%{{visibility:visible}}{end:.3f}%{{visibility:hidden}}" if i == 0 else
                f"0%{{visibility:hidden}}{start:.3f}%{{visibility:visible}}{end:.3f}%{{visibility:hidden}}")
        css.append(f"@keyframes f{i}{{{keys}}}.f{i}{{animation:f{i} {total:.2f}s step-end infinite}}")
        groups.append(f'<g class="f{i}" visibility="hidden">{frame_svg(snap, caption)}</g>')
    dots = "".join(f'<circle cx="{PAD + 6 + i * 20}" cy="{PAD + 8}" r="6" fill="{c}"/>'
                   for i, c in enumerate(("#f38ba8", "#f9e2af", "#a6e3a1")))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,'
           f'DejaVu Sans Mono,monospace" font-size="{FS}" xml:space="preserve">'
           f'<style>text{{white-space:pre}}{"".join(css)}.cap{{fill:#f9e2af;font-size:13px}}</style>'
           f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>{dots}'
           f'<line x1="0" x2="{width:.0f}" y1="{PAD + BAR + LINES * LH + 4}" y2="{PAD + BAR + LINES * LH + 4}" stroke="#313244"/>'
           f'{"".join(groups)}</svg>')
    with open(OUT, "w") as f:
        f.write(svg)
    return total, len(frames), len(svg)


if __name__ == "__main__":
    home = make_demo_home()
    try:
        total, count, size = write_svg(record(home))
    finally:
        shutil.rmtree(home, ignore_errors=True)
    print(f"wrote {os.path.relpath(OUT, REPO)}: {count} frames, {total:.1f}s, {size // 1024} KB")
