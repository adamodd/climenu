# AGENTS.md

Guidance for anyone, human or AI, changing this project. User-facing docs are in `readme.md`; this file covers design decisions and the constraints behind them.

## What's here

| File | Role |
|---|---|
| `climenu.py` | The Ctrl-G menu. Draws inline below the prompt, runs the chosen command. |
| `clicommands.py` | The user's command list (`COMMANDS`). **User-owned**: never rewrite their entries. |
| `para` | Runs several commands at once; Ctrl-C stops all. A thin wrapper around GNU parallel. |
| `Makefile` | `make install` / `make uninstall` into `~/scripts` (or `DEST=`). |
| `readme.md` | User docs, including the zsh and bash hotkey snippets. |

## Principles

- **Minimal dependencies.** climenu uses only the Python 3 standard library. `para` is POSIX `sh` and needs only GNU parallel. Don't add packages; prefer an existing, well-known tool over custom code when one fits (that's why `para` wraps parallel instead of reimplementing it).
- **Portable to macOS and Linux.** Target macOS Terminal.app, iTerm2 and common Linux terminals; zsh and bash (bash 3.2 on macOS is a known untested gap). Shell scripts must run under `sh` (dash on Linux, bash-as-sh on macOS): no bashisms.
- **Readable over clever.** The owner reads Python but isn't a terminal expert. Keep the explanatory comments that say *why* something is done, write new code in the same style, and prefer a few plain lines to a compact trick.
- **Small scope.** This is a menu for issuing commands. Don't grow it into a framework.

## Terminal rules (climenu)

These come from real bugs. Breaking one brings the bug back.

- **Never clear the screen** (`ESC[2J`, curses `clear()`, the alternate screen). iTerm2 and Terminal.app copy a cleared screen into scrollback, so every redraw ended up there. Draw with cursor moves, `ESC[K` and `ESC[J` only.
- **No curses.** It's full-screen by nature and always clears on resize.
- **The anchor.** The cursor rests on the "anchor" (where the shell left it) between redraws, so the terminal's line rewrapping on resize keeps it in place. If the cursor starts at column 1 the menu starts on that line (`lead=0`), otherwise on the line below (`lead=1`). See `Layout` and `Menu._make_room`.
- **Never write in the last column** of a row (pending-wrap breaks reflow on resize).
- **Mouse: act on release, not press**, or the release report is left in the input for the shell to read as typed text.
- **Exit status is a contract with the shell snippets:** 130 means "closed, nothing printed", so the snippets redraw the prompt in place; 0 means a command ran. If you change this, change both snippets in `readme.md`.
- **Commands run in normal line mode** (`Terminal.set_line_mode`): under bash's `bind -x` the terminal is otherwise still in the line editor's no-echo mode. Python ignores Ctrl-C while a command runs, using a handler rather than `SIG_IGN`, which the command would inherit.
- **Arrow keys come in two forms**, `ESC [ A` and `ESC O A` (the latter when the shell has turned on keypad mode, as oh-my-zsh does).

## para

- Keep it a wrapper: option parsing, the GNU-parallel check, one `exec parallel ...`.
- `--termseq TERM,5000,KILL,25` is deliberate. Parallel's default force-kills after about 0.4 s, which cuts off a server's clean shutdown.
- Jobs get stdin from `/dev/null` (parallel's default). That's what stops keypress-watching dev servers from leaving the terminal in a broken mode. Don't add `--tty`.

## Testing

There's no test suite in the repo yet. Changes so far were checked by running real zsh and bash in a pseudo-terminal with [pyte](https://github.com/selectel/pyte) emulating the screen and its scrollback, sending keys, mouse reports, Ctrl-C and resizes, then checking:

- no `ESC[2J` or `ESC[3J` in the output, and nothing new in scrollback;
- the prompt is redrawn correctly after closing and after running, with one- and two-line prompts;
- commands get echoed, line-mode input;
- Ctrl-C leaves no processes behind (`para`) and no Python traceback (climenu).

pyte doesn't rewrap lines on resize, and drops lines from the top on shrink in a way real terminals don't, so resize results need care. Nothing has been tested inside iTerm2 or Terminal.app themselves.

## Conventions

- Work on `main` unless asked otherwise. Commit messages: a short imperative subject, then a body saying what changed and why.
- Keep `readme.md` in step with behaviour: keys, snippets, requirements, testing status.
- `make install` must never overwrite an existing `clicommands.py`.
