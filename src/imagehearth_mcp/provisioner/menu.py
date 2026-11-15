"""Preguntas por número: una tecla, sin escribir nombres. Solo biblioteca estándar.

Con terminal, cada función lee una tecla sin Enter. Sin terminal (tubería, IDE) lee líneas
con `input()`: un número o Enter. Los tests inyectan un lector de teclas.
"""

import sys
from dataclasses import dataclass

CTRL_C = "\x03"
CTRL_D = "\x04"
ENTER = ("\r", "\n")
BACKSPACE = ("\x7f", "\b")
MAX_SINGLE_KEY = 9
# Para los tests: lector de teclas que sustituye a la terminal cuando no se pasa uno.
DEFAULT_READER = None


class _Back:
    def __repr__(self):
        return "BACK"

    def __bool__(self):
        return False


BACK = _Back()


@dataclass(frozen=True)
class Option:
    key: object
    label: str
    detail: str = ""
    recommended: bool = False


def read_key():
    """Una tecla de la terminal sin esperar a Enter. La terminal se restaura siempre."""
    if sys.platform == "win32":
        import msvcrt

        char = msvcrt.getwch()

        if char in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ""

        if char == CTRL_C:
            raise KeyboardInterrupt

        return char

    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        char = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    if char == "":
        raise KeyboardInterrupt

    return char


class _Reader:
    """`keys`: lee teclas sueltas. `injected`: el lector no es la terminal real."""

    def __init__(self, reader=None):
        reader = reader if reader is not None else DEFAULT_READER
        self.injected = reader is not None
        self.read = reader
        self.keys = reader is not None

        if reader is None and sys.stdin.isatty():
            self.read = read_key
            self.keys = True

    def key(self):
        char = self.read()

        if char in (CTRL_C, CTRL_D):
            raise KeyboardInterrupt

        return char

    def line(self, prompt):
        """Una línea. En la terminal real, con la edición normal; inyectada, con teclas."""
        if not self.injected:
            try:
                return input(prompt).strip()
            except EOFError:
                raise KeyboardInterrupt from None

        print(prompt, end="", flush=True)
        text = ""

        while True:
            char = self.key()

            if char in ENTER:
                print()
                return text.strip()

            if char in BACKSPACE:
                text = text[:-1]
            elif char.isprintable():
                text += char


def _echo(text):
    print(text, flush=True)


def _print_option(number, option, mark=""):
    flag = " (recommended)" if option.recommended else ""
    print(f"  {number}. {mark}{option.label}{flag}")

    for line in option.detail.splitlines():
        print(f"     {line}")


def choose(title, options, default=None, reader=None, allow_back=True, back_label="Back"):
    """Elige una opción por número. Devuelve su `key`, o BACK con 0.

    `default`: la `key` que elige Enter.
    """
    options = list(options)
    keys = [option.key for option in options]
    default = default if default in keys else (keys[0] if keys else None)
    default_number = keys.index(default) + 1 if default in keys else None
    source = _Reader(reader)
    single = source.keys and len(options) <= MAX_SINGLE_KEY

    if title:
        print(f"\n{title}")

    for number, option in enumerate(options, start=1):
        _print_option(number, option)

    if allow_back:
        print(f"  0. {back_label}")

    prompt = f"Choice [{default_number}]: "

    while True:
        if single:
            print(prompt, end="", flush=True)
            char = source.key()

            if char in ENTER:
                _echo(str(default_number))
                return default

            if char == "0" and allow_back:
                _echo("0")
                return BACK

            if char.isdigit() and 1 <= int(char) <= len(options):
                _echo(char)
                return keys[int(char) - 1]

            # Tecla no válida: se ignora sin mensaje.
            print("\r" + " " * len(prompt) + "\r", end="", flush=True)
            continue

        answer = source.line(prompt)

        if not answer:
            return default

        if answer == "0" and allow_back:
            return BACK

        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return keys[int(answer) - 1]

        print(f"Type a number from {'0' if allow_back else '1'} to {len(options)}.")


def ask_line(prompt, reader=None):
    """Una línea de texto. Una línea vacía devuelve ''."""
    return _Reader(reader).line(prompt)


def confirm(question, default=False, reader=None, allow_back=False):
    """Sí o no con una tecla: y/s sí, n o 0 no, Enter el valor por defecto. Con `allow_back`, 0 es BACK."""
    hint = "Y/n" if default else "y/N"
    prompt = f"{question} [{hint}{', 0 back' if allow_back else ''}] "
    source = _Reader(reader)

    while True:
        if source.keys:
            print(prompt, end="", flush=True)
            answer = source.key().lower()
            shown = answer
        else:
            answer = source.line(prompt).lower()
            shown = ""

            if answer in ("yes", "si", "sí"):
                answer = "y"

            if not answer:
                answer = "\n"

        if answer in ENTER:
            if source.keys:
                _echo("y" if default else "n")

            return default

        if answer in ("y", "s"):
            if source.keys:
                _echo(shown)

            return True

        if answer in ("n", "0"):
            if source.keys:
                _echo(shown)

            return BACK if answer == "0" and allow_back else False

        if not source.keys:
            return False

        print("\r" + " " * len(prompt) + "\r", end="", flush=True)


def choose_many(title, options, reader=None, allow_back=True, back_label="Back"):
    """Selección múltiple con todas marcadas. Devuelve las `key` elegidas, o BACK con 0."""
    options = list(options)
    source = _Reader(reader)

    if title:
        print(f"\n{title}")

    for number, option in enumerate(options, start=1):
        _print_option(number, option, mark="[x] ")

    if allow_back:
        print(f"  0. {back_label}")

    prompt = "Enter for all, or numbers separated by commas: "

    while True:
        answer = source.line(prompt)

        if not answer:
            return [option.key for option in options]

        if answer == "0" and allow_back:
            return BACK

        try:
            numbers = [int(part) for part in answer.replace(" ", "").split(",") if part]
        except ValueError:
            numbers = []

        if numbers and all(1 <= number <= len(options) for number in numbers):
            chosen = sorted(set(numbers))
            return [options[number - 1].key for number in chosen]

        print(f"Type numbers from 1 to {len(options)} separated by commas, or press Enter for all.")
