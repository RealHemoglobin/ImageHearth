import sys


def venv_python(venv):
    """Intérprete de un venv: `bin/python` o `Scripts/python.exe`."""
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"

    return venv / "bin" / "python"


def find_venv_python(directory):
    """Intérprete del venv de `directory`: `venv` o, si solo existe ese, `.venv`."""
    python = venv_python(directory / "venv")
    alternative = venv_python(directory / ".venv")

    if not python.exists() and alternative.exists():
        return alternative

    return python
