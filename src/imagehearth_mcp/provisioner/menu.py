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
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
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


ESCAPE = "\x1b"
ESCAPE_WAIT = 0.05
_WINDOWS_ARROWS = {"H": "UP", "P": "DOWN"}
_ANSI_ARROWS = {"A": "UP", "B": "DOWN"}


def read_key():
    """Una tecla de la terminal sin esperar a Enter. La terminal se restaura siempre.

    Las flechas arriba y abajo devuelven "UP" y "DOWN"; Esc solo y las demás teclas
    especiales devuelven "".
    """
    if sys.platform == "win32":
        import msvcrt

        char = msvcrt.getwch()

        if char in ("\x00", "\xe0"):
            return _WINDOWS_ARROWS.get(msvcrt.getwch(), "")

        if char == CTRL_C:
            raise KeyboardInterrupt

        return char

    import os
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        char = _read_byte(os, fd)

        if char == ESCAPE:
            return _read_escape(os, select, fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    if char == "":
        raise KeyboardInterrupt

    return char


def _read_byte(os, fd):
    """Un carácter leído directo del descriptor, sin el búfer de `sys.stdin`.

    Con `sys.stdin.read(1)` Python lee de golpe toda la secuencia de una flecha
    (`Esc [ A`) a su búfer; `select` ya no ve nada en el descriptor y la flecha se perdía.
    """
    data = os.read(fd, 1)

    if not data:
        return ""

    # Un carácter UTF-8 multibyte: se completan los bytes que faltan.
    size = 1 if data[0] < 0xC0 else 2 if data[0] < 0xE0 else 3 if data[0] < 0xF0 else 4

    while len(data) < size:
        more = os.read(fd, 1)

        if not more:
            break

        data += more

    return data.decode("utf-8", errors="ignore")


def _read_escape(os, select, fd):
    """Resto de una secuencia que empieza por Esc, sin bloquear si era Esc solo."""

    def next_char():
        if not select.select([fd], [], [], ESCAPE_WAIT)[0]:
            return ""

        return _read_byte(os, fd)

    if next_char() not in ("[", "O"):
        return ""

    return _ANSI_ARROWS.get(next_char(), "")


class _Reader:
    """`keys`: lee teclas sueltas. `injected`: el lector no es la terminal real."""

    def __init__(self, reader=None):
        reader = reader if reader is not None else DEFAULT_READER
        self.injected = reader is not None
        self.read = reader
        self.keys = reader is not None
        self._pending = []

        if reader is None and sys.stdin.isatty():
            self.read = read_key
            self.keys = True

    def key(self, arrows=False):
        """Una tecla. Con `arrows`, las secuencias en bruto de las flechas pasan a UP/DOWN."""
        char = self._pending.pop() if self._pending else self.read()

        if char in (CTRL_C, CTRL_D):
            raise KeyboardInterrupt

        if arrows and char == ESCAPE and self.injected:
            return self._injected_arrow()

        return char

    def _injected_arrow(self):
        """Esc seguido de `[` u `O` y A/B, venga carácter a carácter de un lector inyectado."""
        try:
            second = self.read()
        except StopIteration:
            return ""

        if second not in ("[", "O"):
            self._pending.append(second)
            return ""

        try:
            third = self.read()
        except StopIteration:
            return ""

        if third in _ANSI_ARROWS:
            return _ANSI_ARROWS[third]

        self._pending.append(third)
        return ""

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


def choose_many(
    title, options, reader=None, allow_back=True, back_label="Back", default=None
):
    """Selección múltiple. Devuelve las `key` elegidas, o BACK con 0.

    `default`: las `key` marcadas al empezar, que elige Enter; con `default=None` están
    todas. Con terminal: flechas, espacio y Enter. Sin ella: números separados por comas.
    """
    options = list(options)
    source = _Reader(reader)
    marked = [option.key for option in options] if default is None else list(default)

    if source.keys and (source.injected or _enable_ansi()):
        return _choose_many_keys(title, options, source, marked, allow_back, back_label)

    return _choose_many_line(title, options, source, marked, allow_back, back_label, default)


def _enable_ansi():
    """Activa las secuencias ANSI de la consola. Siempre cierto fuera de Windows."""
    if sys.platform != "win32":
        return True

    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()

        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True

        return bool(kernel.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except (AttributeError, OSError):
        return False


def _selector_lines(options, marked, cursor, allow_back, back_label, show_cursor=True):
    rows = len(options)
    hint = "\u2191/\u2193 move \u00b7 Space mark \u00b7 Enter install"
    lines = [hint + (" \u00b7 0 back" if allow_back else "")]

    def pointer(index):
        return "> " if show_cursor and index == cursor else "  "

    for index, option in enumerate(options):
        flag = " (recommended)" if option.recommended else ""
        mark = "[x] " if option.key in marked else "[ ] "
        lines.append(f"{pointer(index)}{mark}{option.label}{flag}")
        lines.extend(f"       {line}" for line in option.detail.splitlines())

    lines.append(f"{pointer(rows)}\u2192 Install selected ({len(marked)})")

    if allow_back:
        lines.append(f"{pointer(rows + 1)}\u2190 {back_label}")

    return lines


def _choose_many_keys(title, options, source, marked, allow_back, back_label):
    rows = len(options) + 1 + (1 if allow_back else 0)
    install_row = len(options)
    back_row = install_row + 1 if allow_back else None
    cursor = 0
    drawn = 0

    if title:
        print(f"\n{title}")

    def draw(show_cursor=True):
        nonlocal drawn
        lines = _selector_lines(options, marked, cursor, allow_back, back_label, show_cursor)

        if drawn:
            print(f"\x1b[{drawn}A\r\x1b[J", end="")

        print("\n".join(lines), flush=True)
        drawn = len(lines)

    def chosen():
        return [option.key for option in options if option.key in marked]

    while True:
        draw()
        char = source.key(arrows=True)

        if char == "UP":
            cursor = (cursor - 1) % rows
        elif char == "DOWN":
            cursor = (cursor + 1) % rows
        elif char == " " and cursor < len(options):
            key = options[cursor].key
            marked = [k for k in marked if k != key] if key in marked else [*marked, key]
        elif char == "0" and allow_back:
            return BACK
        elif char in ENTER:
            if cursor == back_row:
                return BACK

            draw(show_cursor=False)
            names = ", ".join(str(option.key) for option in options if option.key in marked)
            print(f"Selected: {names or 'none'}", flush=True)
            return chosen()


def _choose_many_line(title, options, source, marked, allow_back, back_label, default):
    if title:
        print(f"\n{title}")

    for number, option in enumerate(options, start=1):
        _print_option(number, option, mark="[x] " if option.key in marked else "[ ] ")

    if allow_back:
        print(f"  0. {back_label}")

    if default is None:
        prompt = "Enter for all, or numbers separated by commas: "
    else:
        prompt = "Enter to keep the marked ones, numbers separated by commas, or none: "

    while True:
        answer = source.line(prompt)

        if not answer:
            return [option.key for option in options if option.key in marked]

        if answer == "0" and allow_back:
            return BACK

        if default is not None and answer.lower() == "none":
            return []

        try:
            numbers = [int(part) for part in answer.replace(" ", "").split(",") if part]
        except ValueError:
            numbers = []

        if numbers and all(1 <= number <= len(options) for number in numbers):
            chosen = sorted(set(numbers))
            return [options[number - 1].key for number in chosen]

        print(
            f"Type numbers from 1 to {len(options)} separated by commas, or press Enter "
            f"{'for all' if default is None else 'to keep the marked ones'}."
        )
