# Tests for the kit itself; see docs/guide.md.
.PHONY: test

test:
	python3 -W ignore::ResourceWarning -m unittest discover tests
