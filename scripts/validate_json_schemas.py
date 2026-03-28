from pathlib import Path
import json
import sys

try:
    from jsonschema.validators import Draft202012Validator
except ImportError:
    print("Missing dependency: jsonschema")
    print("Install with: pip install jsonschema")
    sys.exit(1)

paths = list(Path("contracts/schemas").glob("*.json")) + list(Path("contracts/events").glob("*.json"))

if not paths:
    print("No JSON Schema files found.")
    sys.exit(0)

failed = False
for path in paths:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        print(f"OK: {path}")
    except Exception as e:
        failed = True
        print(f"FAIL: {path}: {e}")

sys.exit(1 if failed else 0)
