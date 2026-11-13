# climenu

Launch `climenu.py` from any shell prompt with **Ctrl-G**. The menu opens right below your prompt; selecting an item runs it immediately, same as running the script directly.

**Using the menu:** Up/Down or the mouse wheel to move, Enter or a click to run, an item's hotkey to jump to it and run it, `q` or Esc to close without running anything.

## Install

From the project folder:

```bash
make install
```

This copies `climenu.py` and `clicommands.py` into `~/scripts`. To use a different folder, pass `DEST`, e.g. `make install DEST=$HOME/bin` (and change `~/scripts` in the snippets below to match). `clicommands.py` must sit in the same folder as the script.

Run `make install` again after pulling changes: it updates `climenu.py` but keeps your edited `clicommands.py`. `make uninstall` removes the script and leaves your `clicommands.py` alone.

## Shell hotkey install

### zsh

Add to `~/.zshrc`:

```zsh
climenu-widget() {
  zle -I                                        # hand the terminal over cleanly
  python3 ~/scripts/climenu.py </dev/tty   # runs the chosen command itself
  if (( $? == 130 )); then                      # closed without running anything:
    zle reset-prompt                            #   redraw the prompt where it was
  fi
}
zle -N climenu-widget
bindkey '^G' climenu-widget
```

Then reload: `source ~/.zshrc`

### bash

Add to `~/.profile` (where your aliases live) or `~/.bashrc`:

```bash
if [[ $- == *i* ]]; then                        # interactive shells only
  __climenu() {
    python3 ~/scripts/climenu.py </dev/tty # runs the chosen command itself
    (( $? == 130 )) || return 124               # a command ran: redraw the whole prompt below it
  }
  bind -x '"\C-g": __climenu'
fi
```

Then reload: `source ~/.profile` (or `~/.bashrc`)

If bash is a login shell and you have a `~/.bash_profile`, bash reads that instead of `~/.profile`. Put the snippet there, or have `~/.bash_profile` source `~/.profile`.

## Notes

- **Changing the key:** edit `^G` (zsh) and `\C-g` (bash). Avoid Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-S and Ctrl-Q, which the terminal uses for signals and flow control.
- **Interactive guard (bash):** required. The menu runs commands in non-interactive `bash -l -c ...` shells that also read `~/.profile`, and `bind -x` errors there. The guard also prevents the menu from launching itself recursively.
- **Typed text:** anything already typed at the prompt is preserved while the menu runs.
- **Exit status 130:** the script exits with 130 when you close the menu without running anything, and 0 when it ran a command. The snippets use this to redraw the prompt in the right place. In zsh, `zle reset-prompt` after a command would draw the new prompt over the last line of its output, so it's only used when nothing ran. In bash, `return 124` makes bash redraw the whole prompt after a command, not just its last line (matters for two-line prompts).
- **Scrollback:** the menu draws below the prompt and never clears the screen, so it leaves nothing in your scrollback, and it erases itself when it closes. A command's output stays on screen like any other command's. If you shrink the window shorter than the menu while it's open, the terminal itself pushes the lines above into scrollback, as it would for any program.
- **Mouse:** clicks and the wheel need mouse reporting turned on: in iTerm2, Settings → Profiles → Terminal → "Enable mouse reporting" (on by default); in Terminal.app, View → Allow Mouse Reporting (⌘R). While the menu is open it receives your clicks, so close it before selecting text with the mouse (or hold Option in iTerm2).
- **Status:** tested in pseudo-terminals on Linux with zsh 5.9 and bash 5.2: closing, running, typed input to a command, Ctrl-C, mouse, resizing, long lists, one- and two-line prompts. Not yet tested inside iTerm2 or Terminal.app themselves, or with macOS's built-in bash 3.2 (Homebrew's bash is 5.x).
