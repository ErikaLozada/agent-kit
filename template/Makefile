# Commands for people and agents alike; see AGENTS.md. Settings: agent-kit.conf.
.PHONY: test report status deploy setup task finish

test:
	@bash scripts/test.sh

report:
	@if [ -f scripts/report.py ]; then python3 scripts/report.py; else echo "no scripts/report.py yet: add one that generates docs/STATUS.md"; fi

status:
	@bash scripts/status.sh

deploy:
	@bash scripts/deploy.sh

setup:
	git config core.hooksPath .githooks
	@echo "git hooks on: .githooks/pre-commit runs make test and guards PROTECTED files"

task:
	@bash scripts/new-task.sh "$(NAME)" "$(OWNER)"

finish:
	@bash scripts/finish-task.sh "$(NAME)"
