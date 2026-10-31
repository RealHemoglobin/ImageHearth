import sys


def venv_python(venv):
    """Intérprete de un venv: `bin/python` o `Scripts/python.exe`."""
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"

    return venv / "bin" / "python"
