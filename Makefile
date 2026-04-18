.PHONY: test coverage lint format typecheck install-hooks run-hooks

test:
	uv run pytest tests

coverage:
	uv run pytest tests --cov=rekordbox_edit --junitxml=.coverage/junit.xml --cov-report=term-missing --cov-report=html --cov-report=xml

lint:
	uv run ruff check --fix

format:
	uv run ruff format

typecheck:
	uv run ty check

install-hooks:
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

run-hooks:
	uv run pre-commit run --all-files
