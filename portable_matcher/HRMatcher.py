import sys

from hr_matcher.app import _default_aliases_path
from hr_matcher.gui import main


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        print("HR Matcher smoke test OK")
        print(f"aliases={_default_aliases_path()}")
        raise SystemExit(0)
    raise SystemExit(main())
