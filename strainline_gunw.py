"""Compatibility entry point; processor implementation lives in backend.gunw_reader."""
from backend.gunw_reader import main
if __name__ == "__main__":
    raise SystemExit(main())
