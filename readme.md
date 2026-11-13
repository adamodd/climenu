# climenu

Two small shell tools for macOS and Linux.

- ⌨️ **climenu**: your command shortcuts in a menu under the prompt. Press Ctrl-G.
- ⚡ **para**: run several commands at once. One Ctrl-C stops them all.

![climenu demo: Ctrl-G opens the menu under the prompt, q closes it without a trace, a hotkey runs git status, and a menu item starts two dev servers with para, which Ctrl-C stops](demo/climenu-demo.svg)

## Requirements

- macOS or Linux
- Python 3 (standard library only) for climenu
- zsh or bash for the Ctrl-G hotkey. Menu commands run in `$SHELL`: bash, zsh or fish.
- [GNU parallel](https://www.gnu.org/software/parallel/) for para: `brew install parallel` / `apt install parallel`. Not the `parallel` from moreutils; para checks.

## Install

```bash
make install                  # into ~/scripts
make install DEST=$HOME/bin   # or elsewhere
make uninstall
```

Installs `climenu.py`, `clicommands.py` and `para`. Reinstalling updates the scripts and never touches your `clicommands.py`.

## climenu

### Keys

| Key | Action |
|---|---|
| ↑ ↓, wheel | move |
| Enter, click | run |
| hotkey | run that item |
| `q`, Esc | close |

Commands run in your normal terminal, so `htop`, `ssh` and `vim` work. You can also run the menu directly: `python3 ~/scripts/climenu.py`.

### Commands

Edit `~/scripts/clicommands.py`. One entry per row:

```python
{"command": "git status", "label": "Git status", "hotkey": "g", "cd": "~/code/myrepo"},
```

Only `command` is required. `hotkey` is one key (not `q`). `cd` sets the folder.

### Hotkey setup

**zsh** (`~/.zshrc`):

```zsh
climenu-widget() {
  zle -I                                   # hand over the terminal
  python3 ~/scripts/climenu.py </dev/tty   # runs the chosen command
  if (( $? == 130 )); then                 # closed without running:
    zle reset-prompt                       #   redraw prompt in place
  fi
}
zle -N climenu-widget
bindkey '^G' climenu-widget
```

**bash** (`~/.profile` or `~/.bashrc`; use `~/.bash_profile` if that's what your login shell reads):

```bash
if [[ $- == *i* ]]; then                   # interactive shells only (required)
  __climenu() {
    python3 ~/scripts/climenu.py </dev/tty # runs the chosen command
    (( $? == 130 )) || return 124          # ran something: redraw full prompt
  }
  bind -x '"\C-g": __climenu'
fi
```

Then `source` the file. To change the key, edit `^G` / `\C-g`. Avoid Ctrl-C, D, Z, S and Q.

### Mouse 🖱️

Needs mouse reporting on:

- **iTerm2:** Settings → Profiles → Terminal → Enable mouse reporting (default on)
- **Terminal.app:** View → Allow Mouse Reporting (⌘R)

While the menu is open it captures clicks. Hold Option in iTerm2 to select text.

### How it works

- **No screen clearing.** The menu is drawn inline with escape codes and erased on close. iTerm2 and Terminal.app copy cleared screens into scrollback, so climenu never clears. Nothing ends up in your scrollback.
- **Your shell, your aliases.** Commands run via `$SHELL -l -c`. See `_shell_invocation()`.
- **Normal input.** The terminal is put back in line mode before a command runs, so prompts like `[Y/n]` work. Ctrl-C stops the command, not climenu.
- **Exit status.** 0 = ran a command, 130 = closed. The snippets use it to redraw the prompt correctly: zsh's `reset-prompt` would overwrite output, and bash's `return 124` redraws multi-line prompts.
- **Typed text is kept** at the prompt.
- **The bash `$-` guard** stops `bind -x` erroring in the non-interactive shells commands run in, and stops the menu launching itself.

## para

```bash
para 'npm run dev' 'python3 -m http.server' 'cd api && make watch'
para -t 'npm run dev' 'python3 -m http.server'   # label output lines
```

One quoted command per argument. Ctrl-C stops everything. `-h` shows usage. Works as a climenu entry too.

### How it works

A thin wrapper around GNU parallel:

```bash
parallel --will-cite --termseq TERM,5000,KILL,25 --line-buffer [--tag] -j0 ::: 'cmd 1' 'cmd 2' ...
```

| Flag | Why |
|---|---|
| `-j0` | run all at once (default is one per CPU core) |
| `--line-buffer` | stream output, whole lines only |
| `--tag` | from `-t`: prefix lines with their command |
| `--termseq TERM,5000,KILL,25` | on Ctrl-C: TERM, up to 5 s for a clean exit, then KILL. The default kills after ~0.4 s. |
| `--will-cite` | no citation notice |

Compared with `trap 'kill $(jobs -p)' EXIT; foo & bar & wait`:

- ✅ Stops child processes too (the `node` behind `npm run dev`).
- ✅ Waits until everything has exited. No stragglers.
- ✅ Commands get no stdin, so keypress-watching dev servers can't leave your terminal in raw mode. That was the cause of the garbled fzf Ctrl-R (`^R ^[^[^C`).

Exit status: 0 if all succeeded, else the number that failed (max 100). 255 after Ctrl-C.

## Testing status

Tested on Linux in pseudo-terminals:

- **climenu:** zsh 5.9, bash 5.2. Close, run, command input, Ctrl-C, mouse, resize, long lists, one- and two-line prompts.
- **para:** dash and bash `--posix`, GNU parallel 20231122. Ctrl-C with slow and TERM-ignoring commands, `-t`, missing parallel.

Not yet tested in iTerm2 or Terminal.app directly, or with macOS's bash 3.2.

## Contributing

Design notes and constraints: [AGENTS.md](AGENTS.md). `CLAUDE.md` points Claude Code there.
