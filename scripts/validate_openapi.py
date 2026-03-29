from pathlib import Path
import sys
import yaml

try:
    from openapi_spec_validator import validate_spec
except ImportError:
    print("Missing dependency: openapi-spec-validator")
    print("Install with: pip install openapi-spec-validator pyyaml")
    sys.exit(1)

base = Path("contracts/api")
files = list(base.glob("*.yaml")) + list(base.glob("*.yml"))

if not files:
    print("No OpenAPI files found.")
    sys.exit(0)

failed = False
for file in files:
    try:
        with file.open("r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        validate_spec(spec)
        print(f"OK: {file}")
    except Exception as e:
        failed = True
        print(f"FAIL: {file}: {e}")

sys.exit(1 if failed else 0)
