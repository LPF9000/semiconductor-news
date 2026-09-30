"""Isolate blocking workspace commands behind a structured subprocess protocol."""

import json
import sys
from pathlib import Path

from .workspace import execute_data


def main() -> None:
    try:
        parts, store, config = json.loads(sys.argv[1])
        result = execute_data(parts, Path(store), Path(config))
        response = {"ok": True, "result": result}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        response = {"ok": False, "error": str(exc)}
    print(json.dumps(response))


if __name__ == "__main__":
    main()
