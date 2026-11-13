# Install climenu into the folder where you keep your own scripts.
#
#   make install                    copy into ~/scripts
#   make install DEST=$HOME/bin     copy somewhere else
#   make uninstall                  remove it again (same DEST)
#
# clicommands.py is copied only the first time. After that it's yours: running
# `make install` again updates climenu.py but never overwrites your
# shortcuts.

DEST ?= $(HOME)/scripts

.PHONY: install uninstall

install:
	install -d "$(DEST)"
	install -m 755 climenu.py "$(DEST)/climenu.py"
	@if [ -e "$(DEST)/clicommands.py" ]; then \
		echo "kept your existing $(DEST)/clicommands.py"; \
	else \
		install -m 644 clicommands.py "$(DEST)/clicommands.py"; \
	fi

uninstall:
	rm -f "$(DEST)/climenu.py"
	@echo "left $(DEST)/clicommands.py in place (your shortcuts); delete it yourself if you don't want it"
