"""
clicommands.py — your command shortcuts, decoupled from climenu.py's logic.

Edit COMMANDS below; climenu.py imports it and doesn't need to change.

Each entry is a dict with these keys:
    "command"  (required) shell command to run
    "label"    (optional) text shown in the menu, right-aligned
    "hotkey"   (optional) single key that jumps to and runs the item
                          (any key but q, which closes the menu)
    "cd"       (optional) directory to change to before running the command
                          (~ is expanded; applies to this item only)

Omit any optional key you don't need.
"""

COMMANDS = [
    {"command": "sudo apt update && sudo apt upgrade -y", "label": "Update system",     "hotkey": "u"},
    {"command": "df -h",                                  "label": "Disk usage",        "hotkey": "d"},
    {"command": "htop || top",                            "label": "Processes (top)",   "hotkey": "p"},
    {"command": "ls -lah",                                "label": "List files (long)", "hotkey": "l"},
    {"command": "git status",                             "label": "Git status",        "hotkey": "g", "cd": "~/path/to/repo"},
    {"command": "ip a || ifconfig",                       "label": "Network info"},
    {"command": "ssh user@example.com",                   "label": "SSH to server",     "hotkey": "s"},
    {"command": "docker system prune -f",                                                 "hotkey": "c"},
    {"command": f"${{EDITOR:-nano}} {__file__}",          "label": "Edit shortcuts",    "hotkey": "e"},
]
