#!/usr/bin/env python
"""Валидация ``cases.yaml`` — согласованного списка тест-кейсов.

``cases.yaml`` — это то, что уходит в промпт агента `test-writer` путями,
а не текстом. Ошибка в нём обнаружится только после генерации тестов,
поэтому файл проверяется до неё.

    uv run python scripts/validate_cases.py .claude/tmp/<id>/cases.yaml

Проверяется:

* обязательные поля у каждого кейса;
* уникальность ``id`` и формат ``TC-NNN``;
* ``endpoint`` существует в ``contracts/openapi.json`` — снапшоте
  live-контракта стенда;
* ``action: edit`` требует ``existing_test``;
* допустимые значения ``profile``, ``priority``, ``source``;
* один ``target_file`` не делится между разными ``action``-режимами так,
  чтобы два агента писали в него параллельно.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "contracts" / "openapi.json"

REQUIRED = ("id", "endpoint", "profile", "action", "target_file", "title", "expect")
PROFILES = {"http", "sse", "llm", "job", "ratelimit"}
ACTIONS = {"new", "edit"}
PRIORITIES = {"blocker", "critical", "normal"}
SOURCES = {"код", "контракт", "план", "инференс"}
_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def known_endpoints() -> set[str]:
    import json

    if not SPEC_PATH.exists():
        raise SystemExit(
            "нет contracts/openapi.json — сними со стенда:\n"
            "    python scripts/openapi_snapshot.py --dump"
        )
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    return {
        f"{method.upper()} {path}"
        for path, item in spec.get("paths", {}).items()
        for method in item
        if method in _HTTP_METHODS
    }


def validate(path: Path) -> list[str]:
    import yaml

    problems: list[str] = []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        return ["корень файла должен быть объектом с ключом 'cases'"]

    for key in ("task", "plan", "cases"):
        if key not in data:
            problems.append(f"нет обязательного ключа '{key}'")

    plan = data.get("plan")
    if plan and not (REPO_ROOT / plan).exists():
        problems.append(f"plan: файла {plan} не существует")

    cases = data.get("cases") or []
    if not isinstance(cases, list) or not cases:
        problems.append("'cases' должен быть непустым списком")
        return problems

    endpoints = known_endpoints()
    seen_ids: set[str] = set()
    files_by_action: dict[str, set[str]] = {}

    for index, case in enumerate(cases):
        label = case.get("id") if isinstance(case, dict) else f"#{index}"

        if not isinstance(case, dict):
            problems.append(f"{label}: кейс должен быть объектом")
            continue

        for field in REQUIRED:
            if not case.get(field):
                problems.append(f"{label}: нет обязательного поля '{field}'")

        case_id = str(case.get("id", ""))
        if case_id:
            if not (
                case_id.startswith("TC-")
                and case_id[3:].isdigit()
                and len(case_id) == 6
            ):
                problems.append(f"{label}: id должен быть вида TC-001")
            if case_id in seen_ids:
                problems.append(f"{label}: дубль id")
            seen_ids.add(case_id)

        endpoint = case.get("endpoint")
        if endpoint and " ".join(str(endpoint).split()) not in endpoints:
            problems.append(
                f"{label}: ручки '{endpoint}' нет в contracts/openapi.json. "
                "Новая ручка → scripts/openapi_snapshot.py --dump"
            )

        profile = case.get("profile")
        if profile and profile not in PROFILES:
            problems.append(
                f"{label}: profile '{profile}' — допустимо {sorted(PROFILES)}"
            )

        action = case.get("action")
        if action and action not in ACTIONS:
            problems.append(f"{label}: action '{action}' — допустимо {sorted(ACTIONS)}")
        if action == "edit" and not case.get("existing_test"):
            problems.append(
                f"{label}: action 'edit' требует 'existing_test' — "
                "имя правимого теста, иначе писатель напишет дубль"
            )

        priority = case.get("priority")
        if priority and priority not in PRIORITIES:
            problems.append(
                f"{label}: priority '{priority}' — допустимо {sorted(PRIORITIES)}"
            )

        source = case.get("source")
        if source and source not in SOURCES:
            problems.append(f"{label}: source '{source}' — допустимо {sorted(SOURCES)}")

        target = case.get("target_file")
        if target:
            if not str(target).startswith("tests/"):
                problems.append(f"{label}: target_file должен быть внутри tests/")
            if action in ACTIONS:
                files_by_action.setdefault(str(target), set()).add(action)

    for target, actions in sorted(files_by_action.items()):
        if len(actions) > 1:
            problems.append(
                f"{target}: в файл идут кейсы и 'new', и 'edit' — раздели их "
                "по файлам либо отдай одному писателю, иначе два агента "
                "будут писать в один файл"
            )

    return problems


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("использование: validate_cases.py <путь к cases.yaml>")

    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"нет файла {path}")

    problems = validate(path)
    if problems:
        print(f"{path}: {len(problems)} проблем(ы)")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"{path}: ок")
    return 0


if __name__ == "__main__":
    sys.exit(main())
