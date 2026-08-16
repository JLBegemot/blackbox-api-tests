#!/bin/sh
# PostToolUse: форматирует записанный .py файл через ruff.
#
# Модель забывает форматировать, хук — нет. Работает только по .py и только
# по файлам внутри репозитория; всё остальное пропускает молча.
#
# Никогда не роняет вызов: ruff нет или файл не парсится — просто выходим 0.
# Синтаксическую ошибку поймает pytest, а не этот хук.

set -eu

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')

[ -n "$FILE" ] || exit 0

case "$FILE" in
  *.py) ;;
  *) exit 0 ;;
esac

case "$FILE" in
  "$ROOT"/*) ;;
  /*) exit 0 ;;   # файл вне репозитория — не наше дело
esac

[ -f "$FILE" ] || exit 0

cd "$ROOT"
uv run ruff format -q "$FILE" >/dev/null 2>&1 || exit 0
exit 0
