# Install profile-menu into the folder where you keep your own scripts.
#
#   make install                    copy into ~/scripts
#   make install DEST=$HOME/bin     copy somewhere else
#   make uninstall                  remove it again (same DEST)
#
# items.py is copied only the first time. After that it's yours: running
# `make install` again updates profile-menu.py but never overwrites your
# shortcuts.

DEST ?= $(HOME)/scripts

.PHONY: install uninstall

install:
	install -d "$(DEST)"
	install -m 755 profile-menu.py "$(DEST)/profile-menu.py"
	@if [ -e "$(DEST)/items.py" ]; then \
		echo "kept your existing $(DEST)/items.py"; \
	else \
		install -m 644 items.py "$(DEST)/items.py"; \
	fi

uninstall:
	rm -f "$(DEST)/profile-menu.py"
	@echo "left $(DEST)/items.py in place (your shortcuts); delete it yourself if you don't want it"
