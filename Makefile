.DEFAULT_GOAL := help

TEST_REGION ?= us-west-2
TEST_ROLE ?= arn:aws:iam::303467602807:role/github-backup-tester
TEST_SELECTOR ?= tests/
TEST_FILTER ?= "test_"

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
    match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
    if match:
        target, help = match.groups()
        print("%-40s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

help:  ## Show this help message
	@python -c "$$PRINT_HELP_PYSCRIPT" < Makefile

.PHONY: install-hooks
install-hooks:  ## Install repo hooks
	@echo "Checking and installing hooks"
	@test -d .git/hooks || (echo "Looks like you are not in a Git repo" ; exit 1)
	@test -L .git/hooks/pre-commit || ln -fs ../../hooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@test -L .git/hooks/commit-msg || ln -fs ../../hooks/commit-msg .git/hooks/commit-msg
	@chmod +x .git/hooks/commit-msg

.PHONY: bootstrap
bootstrap: install-hooks  ## Bootstrap the development environment
	pip install -U "pip ~= 24.0"
	pip install -U "setuptools ~= 75.0"
	pip install -r requirements.txt

.PHONY: test
test:  ## Run tests on the module
	pytest -xvvs \
		--aws-region=${TEST_REGION} \
		--test-role-arn=${TEST_ROLE} \
		$(if ${TEST_FILTER},-k ${TEST_FILTER}) \
		$(TEST_SELECTOR) \
		2>&1 | tee pytest-`date +%Y%m%d-%H%M%S`-output.log

.PHONY: test-keep
test-keep:  ## Run tests and keep infrastructure for debugging
	pytest -xvvs \
		--aws-region=${TEST_REGION} \
		--test-role-arn=${TEST_ROLE} \
		--keep-after \
		$(if ${TEST_FILTER},-k ${TEST_FILTER}) \
		$(TEST_SELECTOR) \
		2>&1 | tee pytest-`date +%Y%m%d-%H%M%S`-output.log

.PHONY: test-clean
test-clean:  ## Run tests and clean up all resources
	pytest -xvvs \
		--aws-region=${TEST_REGION} \
		--test-role-arn=${TEST_ROLE} \
		$(if ${TEST_FILTER},-k ${TEST_FILTER}) \
		$(TEST_SELECTOR) \
		2>&1 | tee pytest-`date +%Y%m%d-%H%M%S`-output.log

.PHONY: clean
clean:  ## Clean build artifacts and caches
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -name '.terraform' -exec rm -fr {} +
	find . -name '.terraform.lock.hcl' -delete

.PHONY: fmt
fmt: format

.PHONY: format
format:  ## Format all code
	terraform fmt -recursive
	black tests container

.PHONY: lint
lint:  ## Run linters in check mode
	terraform fmt -check -recursive
	black --check tests container

.PHONY: release-patch
release-patch:  ## Release a patch version
	git-cliff --tag $$(bumpversion --dry-run --list patch | grep ^new_version | cut -d= -f2) -o CHANGELOG.md
	bumpversion patch
	git push && git push --tags

.PHONY: release-minor
release-minor:  ## Release a minor version
	git-cliff --tag $$(bumpversion --dry-run --list minor | grep ^new_version | cut -d= -f2) -o CHANGELOG.md
	bumpversion minor
	git push && git push --tags

.PHONY: release-major
release-major:  ## Release a major version
	git-cliff --tag $$(bumpversion --dry-run --list major | grep ^new_version | cut -d= -f2) -o CHANGELOG.md
	bumpversion major
	git push && git push --tags
