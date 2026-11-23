# Commands for people and agents alike; see AGENTS.md. Settings: agent-kit.conf.
.PHONY: test status deploy setup task finish worker review diagram

test:
	@bash scripts/test.sh

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

review:
	@DRY="$(DRY)" REVIEW_CMD="$(REVIEW_CMD)" bash scripts/review.sh "$(KIND)" "$(BASE)" "$(MODEL)"

worker:
	@DRY="$(DRY)" TIER="$(TIER)" WORKER_CMD="$(WORKER_CMD)" bash scripts/start-worker.sh "$(NAME)" "$(KIND)" "$(OWNER)" "$(MODEL)" "$(EFFORT)"

diagram:
	@bash scripts/diagram.sh
