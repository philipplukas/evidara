"""Offline JSON Schema validation against repo contracts."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jsonschema import FormatChecker, RefResolver, validators


def validate_instance_against_contract(instance: Any, schema_relative_path: str) -> None:
    schema = load_contract_schema(schema_relative_path)
    validator = build_contract_validator(schema_relative_path)
    validator.validate(instance)


def load_contract_schema(schema_relative_path: str) -> Dict[str, Any]:
    schema_path = _contracts_root() / schema_relative_path
    with schema_path.open("r", encoding="utf-8") as schema_file:
        return json.load(schema_file)


def load_contract_example(example_filename: str) -> Dict[str, Any]:
    example_path = _contracts_root() / "examples" / example_filename
    with example_path.open("r", encoding="utf-8") as example_file:
        return json.load(example_file)


def build_contract_validator(schema_relative_path: str):
    schema = load_contract_schema(schema_relative_path)
    validator_cls = validators.validator_for(schema)
    validator_cls.check_schema(schema)
    resolver = RefResolver.from_schema(schema, store=_schema_store())
    return validator_cls(
        schema,
        resolver=resolver,
        format_checker=FormatChecker(),
    )


@lru_cache(maxsize=1)
def _schema_store() -> Dict[str, Dict[str, Any]]:
    store: Dict[str, Dict[str, Any]] = {}
    for schema_path in _contracts_root().rglob("*.json"):
        if "examples" in schema_path.parts:
            continue
        with schema_path.open("r", encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        schema_id = schema.get("$id")
        if schema_id:
            store[str(schema_id)] = schema
    return store


def _contracts_root() -> Path:
    return Path(__file__).resolve().parents[4] / "contracts"
