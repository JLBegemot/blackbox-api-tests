#!/bin/sh
# PreToolUse-гейт на инструменты MCP-серверов github и linear.
#
# Белый список: разрешено ровно то, что описано в скилле /api-tests
# (.claude/skills/api-tests/SKILL.md, раздел «Источники из MCP»). Всё
# остальное — запрещено, включая любые записи в GitHub (создание PR,
# коммиты, ревью, мерж) и в Linear (создание/правка задач, документов).
#
# Зачем дефолт-ден, а не permissions.deny: deny в settings.json перебивает
# allow, поэтому «запретить сервер целиком, кроме трёх ручек» правилами
# не выражается. Здесь — наоборот: пускаем только перечисленное.
#
# Репозиторий чёрноящичный: MCP нужен исключительно для ЧТЕНИЯ требований
# (Linear-задача, дифф и файлы PR бэкенда). Единственная запись —
# комментарий в Linear-задаче после пуша, и та только с явного
# подтверждения пользователя (SKILL.md, шаг 8).
#
# Выход 2 = запретить вызов инструмента; stderr уходит модели как обратная связь.

set -eu

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL" in
  mcp__github__*|mcp__linear__*) ;;
  *) exit 0 ;;
esac

# Разрешено:
#   linear get_issue / list_comments / get_attachment — задача как ТЗ (шаг 1);
#   linear save_comment — единственная запись, ссылка на MR (шаг 8);
#   github pull_request_read / get_file_contents — дифф PR и файлы из него.
case "$TOOL" in
  mcp__linear__get_issue|mcp__linear__list_comments|mcp__linear__get_attachment|\
mcp__linear__save_comment|\
mcp__github__pull_request_read|mcp__github__get_file_contents)
    exit 0
    ;;
esac

cat >&2 <<EOF
Инструмент '$TOOL' заблокирован политикой проекта.

MCP здесь нужен только для чтения требований в пайплайне /api-tests.
Разрешено ровно это:
  mcp__linear__get_issue, mcp__linear__list_comments,
  mcp__linear__get_attachment, mcp__linear__save_comment,
  mcp__github__pull_request_read, mcp__github__get_file_contents

Прод-код бэкенда живёт в отдельном репозитории и отсюда не правится
(CLAUDE.md, FORBID-010) — записи в GitHub через MCP запрещены.
Ветку, коммит и пуш делает /ship через git, а не MCP.

Нужного факта нет в разрешённых ручках — попроси у пользователя текст
требований или ссылку, не обходи гейт.
EOF
exit 2
