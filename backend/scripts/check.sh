#!/bin/sh
set -eu
ruff check --no-cache app migrations tests
ruff format --check --no-cache app migrations tests
mypy --cache-dir /tmp/medexa-mypy app
pytest -o cache_dir=/tmp/medexa-pytest
