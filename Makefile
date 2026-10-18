# Tests for the kit itself; see README.md.
.PHONY: test

test:
	python3 -W ignore::ResourceWarning -m unittest discover tests
