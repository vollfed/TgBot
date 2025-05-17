import json
import sys
from pathlib import Path

def get_credential(key: str = "TOKEN"):
    """
    Retrieve a specific credential from config.json.
    Always resolves path from project root — works both when run from root and from unit test/main inside src/.
    """
    # Try to resolve project root assuming src/service/LLMService.py is 2 levels down
    candidate_paths = [
        Path(sys.modules['__main__'].__file__).resolve().parent,            # main script location (works from HomeBot)
        Path(__file__).resolve().parents[2],                                # fallback if directly running LLMService
        Path.cwd(),                                                         # as a last resort, current working dir
    ]

    for base in candidate_paths:
        config_path = base / "src" / "resources" / "config.json"
        if config_path.exists():
            break
    else:
        raise FileNotFoundError("Could not locate config.json in expected paths.")

    try:
        with config_path.open() as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON in {config_path}: {e}")

    value = config.get(key)
    if not value:
        raise KeyError(f"Missing '{key}' in config file.")

    return value
