#!/usr/bin/env sh

fail_fast=1
failed_checks=""

usage() {
  cat <<'EOF'
Usage: local-checks.sh [OPTIONS]

Run local quality checks for this project.

Options:
  --no-fail-fast  Continue running all checks even if one fails
  -h, --help      Show this help message
EOF
}

for arg in "$@"; do
  case "$arg" in
    --no-fail-fast)
      fail_fast=0
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

run_check() {
  name="$1"
  shift

  printf '==> %s\n' "$name"
  if "$@"; then
    return 0
  fi

  failed_checks="${failed_checks}  - ${name}
"
  if [ "$fail_fast" -eq 1 ]; then
    printf '\nCheck failed: %s\n' "$name" >&2
    exit 1
  fi
  return 1
}

# ---------------------------------------------------------------------------
# Checks — add, remove, or reorder entries below.
# Each line is: run_check "display name" command [args...]
# ---------------------------------------------------------------------------
run_check "ruff format" uv run ruff format --check .
run_check "ruff lint" uv run ruff check .
run_check "basedpyright" uv run basedpyright
run_check "mypy" uv run mypy .
run_check "pytest" uv run pytest
run_check "pip-audit" uv run pip-audit --skip-editable

if [ -n "$failed_checks" ]; then
  printf '\nThe following checks failed:\n%s' "$failed_checks" >&2
  exit 1
fi

printf '\nAll checks passed.\n'
