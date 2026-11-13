# profile-menu: shell hotkey install

Launch `profile-menu.py` from any shell prompt with **Ctrl-G**. Selecting an item runs it immediately, same as running the script directly.

Replace `~/path/to/profile-menu.py` below with the script's real location. `items.py` must sit in the same directory as the script.

## zsh

Add to `~/.zshrc`:

```zsh
profile-menu-widget() {
  zle -I                                        # hand the terminal over cleanly
  python3 ~/path/to/profile-menu.py </dev/tty   # runs the chosen command itself
  zle reset-prompt                              # redraw prompt when it returns
}
zle -N profile-menu-widget
bindkey '^G' profile-menu-widget
```

Then reload: `source ~/.zshrc`

## bash

Add to `~/.profile` (where your aliases live) or `~/.bashrc`:

```bash
if [[ $- == *i* ]]; then                        # interactive shells only
  __profile_menu() { python3 ~/path/to/profile-menu.py </dev/tty; }
  bind -x '"\C-g": __profile_menu'
fi
```

Then reload: `source ~/.profile` (or `~/.bashrc`)

If bash is a login shell and you have a `~/.bash_profile`, bash reads that instead of `~/.profile`. Put the snippet there, or have `~/.bash_profile` source `~/.profile`.

## Notes

- **Changing the key:** edit `^G` (zsh) and `\C-g` (bash). Avoid Ctrl-C, Ctrl-D, Ctrl-Z, Ctrl-S and Ctrl-Q, which the terminal uses for signals and flow control.
- **Interactive guard (bash):** required. The menu runs commands in non-interactive `bash -l -c ...` shells that also read `~/.profile`, and `bind -x` errors there. The guard also prevents the menu from launching itself recursively.
- **Typed text:** anything already typed at the prompt is preserved while the menu runs.
- **Screen:** the script clears the screen before running a command, so the prompt redraws at the top afterward.
- **Status:** the bash binding was tested in a pseudo-terminal. The zsh widget and both snippets in iTerm2 have not been tested; try Ctrl-G once in each shell.
