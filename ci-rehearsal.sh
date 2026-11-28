#!/usr/bin/env bash
# Run from a disposable copy of the project on Ubuntu 24.04 x86_64.
# No Git writes, releases, artifact uploads or deployment.
set -euo pipefail
[[ "$(uname -m)" == x86_64 ]]
[[ "$(python -c 'import platform; print(platform.python_version())')" == 3.13.18 ]]
[[ "$(node --version)" == v22.23.5 ]]
sha256sum requirements-pages.lock
printf '%s  %s\n' 6bc0f75d96e7e9229c8c3a82cf1adc8f4b668542b08d1c056379990542dc4646 requirements-pages.lock | sha256sum -c -
work=$(mktemp -d "${RUNNER_TEMP:-/tmp}/f1-ci.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
python -m venv "$work/project"
p="$work/project/bin/python"
"$p" -m pip download --require-hashes --only-binary=:all: -r requirements-pages.lock --dest "$work/wheels"
sha256sum "$work"/wheels/*
"$p" -m pip install --no-index --find-links "$work/wheels" --require-hashes --only-binary=:all: -r requirements-pages.lock
"$p" -m pip check
"$p" -m pip list --format=freeze
# Auditor has its own environment; never modifies the locked project environment.
python -m venv "$work/auditor"
"$work/auditor/bin/python" -m pip install 'pip-audit==2.10.1'
"$work/auditor/bin/pip-audit" --version
site=$("$p" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
# Fail on known vulnerability, failed network or skipped packages. No ignores or auto-fix.
"$work/auditor/bin/pip-audit" --strict --path "$site"
printf '\nF142_CI_DEPENDENCIES_OK\n'
