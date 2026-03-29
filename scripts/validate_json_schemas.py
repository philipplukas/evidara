from pathlib import Path
import json
import sys

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry
    from referencing.jsonschema import DRAFT202012
except ImportError:
    print("Missing dependency: jsonschema or referencing")
    print("Install with: pip install jsonschema referencing")
    sys.exit(1)


SCHEMA_DIRS = [
    Path("contracts/common"),
    Path("contracts/schemas"),
    Path("contracts/events"),
]

EXAMPLE_TO_SCHEMA = {
    "artifact-bundle-manifest.json": "contracts/schemas/artifact-bundle-manifest.schema.json",
    "processing-manifest.json": "contracts/schemas/processing-manifest.schema.json",
    "document.json": "contracts/schemas/document.schema.json",
    "section.json": "contracts/schemas/section.schema.json",
    "citation.json": "contracts/schemas/citation.schema.json",
    "evidence-ref.json": "contracts/schemas/evidence-ref.schema.json",
    "artifact-bundle-available.json": "contracts/events/artifact-bundle-available.schema.json",
    "document-processing-status-updated.json": "contracts/events/document-processing-status-updated.schema.json",
    "document-processed.json": "contracts/events/document-processed.schema.json",
    "document-withdrawn.json": "contracts/events/document-withdrawn.schema.json",
    "index-update-requested.json": "contracts/events/index-update-requested.schema.json",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


schema_paths = []
for directory in SCHEMA_DIRS:
    schema_paths.extend(sorted(directory.glob("*.json")))

if not schema_paths:
    print("No JSON Schema files found.")
    sys.exit(0)

failed = False
registry = Registry()
schemas_by_path = {}

for path in schema_paths:
    try:
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        if "$id" not in schema or not schema.get("$id"):
            raise ValueError(f"Schema missing required $id field: {path}")
        schema_id = schema["$id"]
        registry = registry.with_resource(schema_id, DRAFT202012.create_resource(schema))
        schemas_by_path[str(path)] = schema
        print(f"OK schema: {path}")
    except Exception as exc:
        failed = True
        print(f"FAIL schema: {path}: {exc}")

examples_dir = Path("contracts/examples")
for example_name, schema_path_str in EXAMPLE_TO_SCHEMA.items():
    example_path = examples_dir / example_name
    schema_path = Path(schema_path_str)

    if not example_path.exists():
        failed = True
        print(f"FAIL example: {example_path}: missing example file")
        continue

    if str(schema_path) not in schemas_by_path:
        failed = True
        print(f"FAIL example: {example_path}: missing schema {schema_path}")
        continue

    try:
        example = load_json(example_path)
        schema = schemas_by_path[str(schema_path)]
        validator = Draft202012Validator(schema, registry=registry)
        validator.validate(example)
        print(f"OK example: {example_path} -> {schema_path}")
    except Exception as exc:
        failed = True
        print(f"FAIL example: {example_path}: {exc}")

sys.exit(1 if failed else 0)