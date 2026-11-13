# climenu

Two small command-line tools for macOS and Linux:

- **climenu**: a menu of your own command shortcuts that pops up under your shell prompt when you press Ctrl-G.
- **xcmd**: runs several commands side by side, such as dev servers, and stops them all with one Ctrl-C.

## Requirements

- **macOS or Linux.**
- **Python 3** for climenu. It uses only the standard library.
- **zsh or bash** for climenu's Ctrl-G hotkey. Commands from the menu run in your own shell (`$SHELL`): bash, zsh and fish are supported. There's no hotkey snippet for fish yet.
- **GNU parallel** for xcmd: `brew install parallel` on macOS, `apt install parallel` on Debian/Ubuntu. Not to be confused with the different `parallel` in the `moreutils` package; xcmd checks for this and tells you.

## Install

From the project folder:

```bash
make install
```

This copies `climenu.py`, `clicommands.py` and `xcmd` into `~/scripts`. To use another folder, pass `DEST`, e.g. `make install DEST=$HOME/bin`, and change `~/scripts` in the snippets below to match.

Run `make install` again after pulling changes. It updates the scripts but never overwrites your edited `clicommands.py`. `make uninstall` removes the scripts and leaves `clicommands.py` alone.

## climenu

### Usage

Press **Ctrl-G** at a shell prompt (after setting up the hotkey below), or run `python3 ~/scripts/climenu.py`. The menu opens right below your prompt.

| Key | Action |
|---|---|
| Up / Down, mouse wheel | move the highlight |
| Enter, click | run the highlighted (clicked) command |
| an item's hotkey | jump to that command and run it |
| `q`, Esc | close without running anything |

The chosen command runs in your normal terminal, so interactive programs like `htop`, `ssh` and `vim` work as usual.

### Adding commands

Edit `~/scripts/clicommands.py`. Each entry in `COMMANDS` is one menu row:

```python
{"command": "git status", "label": "Git status", "hotkey": "g", "cd": "~/code/myrepo"},
```

Only `command` is required. `label` is shown on the right, `hotkey` is a single key (any key but `q`), and `cd` is a folder to run the command in. The file's header explains each field.

### Ctrl-G hotkey

**zsh:** add to `~/.zshrc`, then run `source ~/.zshrc`:

```zsh
climenu-widget() {
  zle -I                                        # hand the terminal over cleanly
  python3 ~/scripts/climenu.py </dev/tty        # runs the chosen command itself
  if (( $? == 130 )); then                      # closed without running anything:
    zle reset-prompt                            #   redraw the prompt where it was
  fi
}
zle -N climenu-widget
bindkey '^G' climenu-widget
```

**bash:** add to `~/.profile` (where your aliases live) or `~/.bashrc`, then `source` it:

```bash
if [[ $- == *i* ]]; then                        # interactive shells only
  __climenu() {
    python3 ~/scripts/climenu.py </dev/tty      # runs the chosen command itself
    (( $? == 130 )) || return 124               # a command ran: redraw the whole prompt below it
  }
  bind -x '"\C-g": __climenu'
fi
```

If bash is a login shell and you have a `~/.bash_profile`, bash reads that instead of `~/.profile`. Put the snippet there, or have `~/.bash_profile` source `~/.profile`.

To use a different key, change `^G` (zsh) or `\C-g` (bash). Avoid Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-S and Ctrl-Q, which the terminal uses for signals and flow control.

### Mouse

Clicks and the wheel need mouse reporting turned on in your terminal:

- **iTerm2:** Settings → Profiles → Terminal → "Enable mouse reporting" (on by default).
- **Terminal.app:** View → Allow Mouse Reporting (⌘R).

While the menu is open it receives your clicks, so close it before selecting text with the mouse (or hold Option in iTerm2).

### How it works

- **Drawn inline, no screen clearing.** The menu is drawn with plain terminal escape codes below the prompt, redrawn in place, and erased when it closes. It never clears the screen, because iTerm2 and Terminal.app copy a cleared screen into scrollback. So it leaves nothing in your scrollback. (If you shrink the window shorter than the menu while it's open, the terminal itself pushes lines above it into scrollback, as it would for any program.)
- **Commands run in your login shell** (`$SHELL -l -c ...`), so your aliases and environment are available. See `_shell_invocation()` in `climenu.py` for the details per shell.
- **Normal terminal mode for commands.** Before running a command, climenu switches the terminal back to normal line-by-line typing, so commands that ask questions work. Ctrl-C stops the command without a Python error.
- **Exit status.** climenu exits with 0 when it ran a command and 130 when you closed it without running anything. The hotkey snippets use this to redraw the prompt in the right place. In zsh, `zle reset-prompt` after a command would draw the new prompt over the last line of its output, so it's only used when nothing ran. In bash, `return 124` makes bash redraw the whole prompt after a command, not just its last line, which matters for two-line prompts.
- **Typed text is kept.** Anything already typed at the prompt is still there when the menu closes.
- **The bash interactive guard is required.** Commands run in non-interactive `bash -l -c ...` shells that also read `~/.profile`, and `bind -x` errors there. The guard also stops the menu from launching itself recursively.

## xcmd

### Usage

```bash
xcmd 'npm run dev' 'python3 -m http.server' 'cd api && make watch'
xcmd -t 'npm run dev' 'python3 -m http.server'
```

Each argument is one command; quote it if it has spaces or `&&`. All of them start at once, and their output is printed as it arrives. Press **Ctrl-C** to stop them all.

| Option | Meaning |
|---|---|
| `-t` | label each output line with the command it came from |
| `-h` | show usage |

It also works as a `command` in `clicommands.py`, so you can start a whole set of dev servers from the menu.

### How it works

xcmd is a short wrapper around GNU parallel, which does the real work. The command it runs is:

```bash
parallel --will-cite --termseq TERM,5000,KILL,25 --line-buffer [--tag] -j0 ::: 'cmd 1' 'cmd 2' ...
```

| Flag | What it does |
|---|---|
| `-j0` | run every command at once (by default parallel runs only as many as you have CPU cores) |
| `--line-buffer` | print output as it arrives, a whole line at a time, so lines from different commands don't get mixed together |
| `--tag` | added by `-t`: start each line with the command that printed it |
| `--termseq TERM,5000,KILL,25` | on Ctrl-C, ask each command to stop, wait up to 5 seconds for it to shut down cleanly, then force it. Parallel's default force-kills after about 0.4 seconds, too soon for a server to finish shutting down |
| `--will-cite` | skip parallel's "please cite GNU parallel" notice |

Why this is better than `trap 'kill $(jobs -p)' EXIT; foo & bar & wait`:

- **Everything is stopped, including what the commands started.** With `cd app && npm run dev`, the `node` process behind npm is stopped too.
- **xcmd doesn't return until everything has exited.** Nothing is left shutting down in the background after your prompt comes back.
- **The commands get no keyboard input.** Dev servers that watch for keypresses switch the terminal into a special mode and switch it back when they exit. Without keyboard input they leave the terminal alone. That's what garbled fzf's Ctrl-R (`^R ^[^[^C`) after the old one-liner.

xcmd exits with parallel's status: 0 if every command succeeded, otherwise the number of commands that failed (up to 100), and 255 if you stopped it with Ctrl-C.

## Testing status

Tested on Linux in pseudo-terminals:

- **climenu**, with zsh 5.9 and bash 5.2: closing, running, typed input to a command, Ctrl-C, mouse, resizing, long lists, and one- and two-line prompts.
- **xcmd**, run by dash and by bash in POSIX mode, with GNU parallel 20231122: Ctrl-C with slow-stopping and stop-ignoring commands, `-t`, and the missing-parallel checks.

Not yet tested inside iTerm2 or Terminal.app themselves, or with macOS's built-in bash 3.2 (Homebrew's bash is 5.x).
