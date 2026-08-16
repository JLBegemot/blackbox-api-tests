#!/usr/bin/env python3
"""Снапшот OpenAPI-контракта: ``contracts/openapi.json``.

В чёрном ящике источник контракта — live-спека поднятого стенда
(``GET {STAND_URL}/openapi.json``), а снапшот в ``contracts/`` версионируется
и держит на себе проектирование тест-кейсов, ``scripts/validate_cases.py``
и гейт маркеров в ``tests/conftest.py``.

Режимы:

* ``--dump``  — забрать live-спеку со стенда и перезаписать снапшот;
* ``--check`` — упасть, если live-спека разошлась со снапшотом (шаг CI,
  он же детектор дрейфа контракта бэкенда).

Только stdlib — гоняется до установки зависимостей тестов.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "contracts" / "openapi.json"
STAND_URL = os.environ.get("STAND_URL", "http://localhost:8000").rstrip("/")

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _load_live_spec() -> dict:
    url = f"{STAND_URL}/openapi.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.load(resp)
    except OSError as exc:
        raise SystemExit(
            f"не достучались до live-спеки {url}: {exc}\n"
            "Стенд поднимается снаружи: проверь, что он запущен и готов "
            "и что STAND_URL указывает на него."
        )


def operations(spec: dict) -> set[tuple[str, str]]:
    """``{("POST", "/api/v1/ai/analyze"), ...}`` — все операции контракта."""

    return {
        (method.upper(), path)
        for path, item in spec.get("paths", {}).items()
        for method in item
        if method in _HTTP_METHODS
    }


def _serialize(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def cmd_dump() -> int:
    spec = _load_live_spec()
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(_serialize(spec), encoding="utf-8")
    print(f"{SPEC_PATH.relative_to(REPO_ROOT)}: {len(operations(spec))} операций")
    return 0


def cmd_check() -> int:
    live = _serialize(_load_live_spec())
    stored = SPEC_PATH.read_text(encoding="utf-8") if SPEC_PATH.exists() else ""

    if live == stored:
        print("live-спека стенда совпадает со снапшотом")
        return 0

    live_ops = operations(json.loads(live))
    stored_ops = operations(json.loads(stored)) if stored else set()

    print("live-спека стенда разошлась со снапшотом contracts/openapi.json:")
    print("    python scripts/openapi_snapshot.py --dump   # принять дрейф осознанно")
    for method, path in sorted(live_ops - stored_ops):
        print(f"  + {method:7} {path}")
    for method, path in sorted(stored_ops - live_ops):
        print(f"  - {method:7} {path}")
    if live_ops == stored_ops:
        print("  (набор операций тот же, различаются схемы или описания)")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dump", action="store_true", help="перезаписать снапшот live-спекой")
    group.add_argument("--check", action="store_true", help="проверить дрейф контракта")
    args = parser.parse_args()

    return cmd_dump() if args.dump else cmd_check()


if __name__ == "__main__":
    sys.exit(main())
