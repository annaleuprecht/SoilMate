# setcwd_hook.py — ensure relative paths work when frozen
import os, sys

def _resource_dir():
    # When frozen by PyInstaller, resources are in a temp folder referenced by _MEIPASS
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS  # type: ignore[attr-defined]
    # When running from source
    return os.path.dirname(os.path.abspath(sys.argv[0]))

os.chdir(_resource_dir())
