import os
import sys
import types

import pytest

from imagehearth_mcp.provisioner import menu
from imagehearth_mcp.provisioner.menu import BACK, Option


def keys(text):
    """Lector inyectable: devuelve las teclas de `text` una a una."""
    chars = iter(text)
    return lambda: next(chars)


OPTIONS = [Option("a", "Alpha"), Option("b", "Beta", recommended=True), Option("c", "Gamma")]


def test_choose_by_number(capsys):
    assert menu.choose("Pick", OPTIONS, default="b", reader=keys("3")) == "c"
    output = capsys.readouterr().out
    assert "1. Alpha" in output and "2. Beta (recommended)" in output and "0. Back" in output
    assert output.rstrip().endswith("3")


def test_choose_enter_takes_the_default():
    assert menu.choose("Pick", OPTIONS, default="b", reader=keys("\r")) == "b"
    assert menu.choose("Pick", OPTIONS, default="a", reader=keys("\n")) == "a"


def test_choose_ignores_invalid_keys():
    assert menu.choose("Pick", OPTIONS, default="a", reader=keys("x9 \x1b[2")) == "b"


def test_choose_zero_goes_back_unless_disallowed():
    assert menu.choose("Pick", OPTIONS, reader=keys("0")) is BACK
    assert menu.choose("Pick", OPTIONS, reader=keys("02"), allow_back=False) == "b"


def test_choose_with_more_than_nine_options_needs_a_number_and_enter():
    many = [Option(n, f"Item {n}") for n in range(1, 13)]
    assert menu.choose("Pick", many, default=2, reader=keys("11\r")) == 11
    assert menu.choose("Pick", many, default=2, reader=keys("\r")) == 2
    # Invalid input asks again; backspace edits.
    assert menu.choose("Pick", many, default=2, reader=keys("99\r1\x7f12\r")) == 12


def test_choose_ctrl_c_raises():
    with pytest.raises(KeyboardInterrupt):
        menu.choose("Pick", OPTIONS, reader=keys("\x03"))


@pytest.mark.parametrize("answer", ["y", "Y", "s", "S"])
def test_confirm_yes(answer):
    assert menu.confirm("Go?", reader=keys(answer)) is True


@pytest.mark.parametrize("answer", ["n", "N"])
def test_confirm_no(answer):
    assert menu.confirm("Go?", default=True, reader=keys(answer)) is False


def test_confirm_enter_and_invalid_keys():
    assert menu.confirm("Go?", reader=keys("\r")) is False
    assert menu.confirm("Go?", default=True, reader=keys("\r")) is True
    assert menu.confirm("Go?", reader=keys("q7y")) is True


def test_confirm_zero_only_goes_back_when_allowed():
    assert menu.confirm("Go?", default=True, reader=keys("0")) is False
    assert menu.confirm("Go?", reader=keys("0"), allow_back=True) is BACK


def test_confirm_ctrl_c_raises():
    with pytest.raises(KeyboardInterrupt):
        menu.confirm("Go?", reader=keys("\x03"))


UP = "\x1b[A"
DOWN = "\x1b[B"
ENTER = "\r"


def run_many(text, **kwargs):
    return menu.choose_many("Pick", OPTIONS, reader=keys(text), **kwargs)


def test_choose_many_enter_accepts_all_marked_by_default(capsys):
    assert run_many(ENTER) == ["a", "b", "c"]
    output = capsys.readouterr().out
    assert "\u2191/\u2193 move \u00b7 Space mark \u00b7 Enter install \u00b7 0 back" in output
    assert "\u2192 Install selected (3)" in output and "\u2190 Back" in output
    assert "Selected: a, b, c" in output


def test_choose_many_moves_and_marks():
    assert run_many(DOWN + " " + ENTER, default=[]) == ["b"]
    assert run_many(DOWN + DOWN + " " + " " + " " + ENTER, default=[]) == ["c"]
    assert run_many(" " + DOWN + " " + ENTER, default=[]) == ["a", "b"]


def test_choose_many_unmarks_and_keeps_the_option_order():
    assert run_many(" " + ENTER) == ["b", "c"]
    assert run_many(DOWN + DOWN + " " + UP + UP + " " + ENTER, default=["b"]) == ["a", "b", "c"]


def test_choose_many_wraps_around_the_ends():
    assert run_many(UP * 3 + " " + ENTER, default=[]) == ["c"]
    # Rows: a, b, c, Install, Back; down from Back returns to a.
    assert run_many(DOWN * 5 + " " + ENTER, default=[]) == ["a"]


def test_choose_many_accepts_names_and_ss3_sequences():
    assert run_many(DOWN + " " + ENTER, default=[]) == ["b"]
    assert run_many("\x1bOB" + " " + ENTER, default=[]) == ["b"]
    assert run_many("\x1bOB\x1bOA" + " " + ENTER, default=[]) == ["a"]
    assert menu.choose_many("Pick", OPTIONS, reader=iter(["DOWN", " ", "\r"]).__next__, default=[]) == ["b"]


def test_choose_many_enter_on_install_and_on_back():
    assert run_many(DOWN * 3 + ENTER, default=["b"]) == ["b"]
    assert run_many(DOWN * 4 + ENTER) is BACK


def test_choose_many_space_on_the_final_rows_does_nothing():
    assert run_many(DOWN * 3 + " " + ENTER, default=["b"]) == ["b"]
    assert run_many(DOWN * 4 + " " + ENTER) is BACK


def test_choose_many_zero_goes_back_from_any_row():
    assert run_many("0") is BACK
    assert run_many(DOWN * 3 + "0") is BACK


def test_choose_many_nothing_marked_returns_an_empty_list(capsys):
    assert run_many(ENTER, default=[]) == []
    assert "Selected: none" in capsys.readouterr().out


def test_choose_many_counter_follows_the_marks(capsys):
    run_many(" " + " " + ENTER, default=[])
    output = capsys.readouterr().out
    assert "Install selected (0)" in output and "Install selected (1)" in output


def test_choose_many_redraws_in_place(capsys):
    run_many(DOWN + ENTER)
    output = capsys.readouterr().out
    # Each redraw moves up over what was drawn: help, 3 options, install and back.
    assert "\x1b[6A" in output and "\x1b[J" in output


def test_choose_many_marks_the_cursor_row(capsys):
    run_many(DOWN + ENTER)
    assert "> [x] Beta" in capsys.readouterr().out


def test_choose_many_without_back_has_no_back_row_and_ignores_zero(capsys):
    assert run_many("0" + " " + ENTER, allow_back=False, default=[]) == ["a"]
    output = capsys.readouterr().out
    assert "\u2190" not in output and "0 back" not in output


def test_choose_many_custom_back_label(capsys):
    run_many("0", back_label="Previous step")
    assert "\u2190 Previous step" in capsys.readouterr().out


def test_choose_many_ignores_unknown_keys_and_a_lone_escape():
    assert run_many("x9\x1b\x1b[Z" + " " + ENTER, default=[]) == ["a"]
    assert run_many("\x1bx" + " " + ENTER, default=[]) == ["a"]


def test_choose_many_ctrl_c_raises():
    with pytest.raises(KeyboardInterrupt):
        run_many("\x03")


# Sin terminal: se lee por línea con input().


@pytest.fixture
def lines(monkeypatch):
    """stdin sin terminal y `input()` simulado con las líneas dadas."""
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))

    def feed(*answers):
        queue = iter(answers)
        monkeypatch.setattr("builtins.input", lambda prompt="": next(queue))

    return feed


def test_line_mode_choose(lines):
    lines("2")
    assert menu.choose("Pick", OPTIONS, default="a") == "b"
    lines("")
    assert menu.choose("Pick", OPTIONS, default="c") == "c"
    lines("0")
    assert menu.choose("Pick", OPTIONS) is BACK
    lines("zzz", "9", "1")
    assert menu.choose("Pick", OPTIONS) == "a"


def test_line_mode_confirm(lines):
    lines("y")
    assert menu.confirm("Go?") is True
    lines("s")
    assert menu.confirm("Go?") is True
    lines("")
    assert menu.confirm("Go?") is False
    lines("")
    assert menu.confirm("Go?", default=True) is True
    lines("n")
    assert menu.confirm("Go?", default=True) is False


def test_line_mode_choose_many(lines, capsys):
    lines("")
    assert menu.choose_many("Pick", OPTIONS) == ["a", "b", "c"]
    lines("1, 3")
    assert menu.choose_many("Pick", OPTIONS) == ["a", "c"]
    lines("0")
    assert menu.choose_many("Pick", OPTIONS) is BACK
    lines("7", "x", "2")
    assert menu.choose_many("Pick", OPTIONS) == ["b"]
    assert "separated by commas" in capsys.readouterr().out
    lines("none")
    assert menu.choose_many("Pick", OPTIONS, default=["a"]) == []
    lines("")
    assert menu.choose_many("Pick", OPTIONS, default=["a"]) == ["a"]


def test_line_mode_end_of_input_is_an_interruption(monkeypatch):
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    with pytest.raises(KeyboardInterrupt):
        menu.choose("Pick", OPTIONS)


# La terminal se restaura siempre.


class FakeTermios:
    TCSADRAIN = 1

    def __init__(self):
        self.calls = []

    def tcgetattr(self, fd):
        self.calls.append("get")
        return ["saved"]

    def tcsetattr(self, fd, when, attrs):
        self.calls.append(("set", attrs))


@pytest.mark.skipif(sys.platform == "win32", reason="termios es de POSIX")
@pytest.mark.parametrize("failure", [None, KeyboardInterrupt])
def test_read_key_restores_the_terminal(monkeypatch, failure):
    fake = FakeTermios()
    fake_tty = types.SimpleNamespace(setcbreak=lambda fd: fake.calls.append("cbreak"))

    class Stdin:
        def fileno(self):
            return 0

    def fake_read(fd, count):
        if failure:
            raise failure

        return b"5"

    monkeypatch.setitem(sys.modules, "termios", fake)
    monkeypatch.setitem(sys.modules, "tty", fake_tty)
    monkeypatch.setattr(sys, "stdin", Stdin())
    monkeypatch.setattr(os, "read", fake_read)

    if failure:
        with pytest.raises(failure):
            menu.read_key()
    else:
        assert menu.read_key() == "5"

    assert fake.calls == ["get", "cbreak", ("set", ["saved"])]


# Lectura de flechas.


class ScriptedStdin:
    def __init__(self, text):
        self.chars = list(text.encode())

    def fileno(self):
        return 0

    def read_byte(self, fd, count):
        return bytes([self.chars.pop(0)]) if self.chars else b""


def posix_terminal(monkeypatch, text):
    """termios, tty y select simulados; `select` dice que hay datos mientras queden."""
    fake = FakeTermios()
    stdin = ScriptedStdin(text)
    monkeypatch.setitem(sys.modules, "termios", fake)
    monkeypatch.setitem(
        sys.modules, "tty", types.SimpleNamespace(setcbreak=lambda fd: fake.calls.append("cbreak"))
    )
    monkeypatch.setitem(
        sys.modules,
        "select",
        types.SimpleNamespace(select=lambda r, w, x, t: (r if stdin.chars else [], [], [])),
    )
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(os, "read", stdin.read_byte)
    monkeypatch.setattr(sys, "platform", "linux")
    return fake


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\x1b[A", "UP"),
        ("\x1b[B", "DOWN"),
        ("\x1bOA", "UP"),
        ("\x1bOB", "DOWN"),
        ("\x1b[C", ""),
        ("\x1b[5", ""),
        ("\x1b", ""),
        ("\x1bx", ""),
        (" ", " "),
    ],
)
def test_read_key_reads_arrows_on_posix(monkeypatch, text, expected):
    fake = posix_terminal(monkeypatch, text)
    assert menu.read_key() == expected
    assert fake.calls == ["get", "cbreak", ("set", ["saved"])]


@pytest.mark.skipif(sys.platform == "win32", reason="pty es de POSIX")
@pytest.mark.parametrize(("text", "expected"), [(b"\x1b[A", "UP"), (b"\x1b[B", "DOWN"), (b"\x1bOB", "DOWN"), (b"\x1b", "")])
def test_read_key_reads_arrows_from_a_real_terminal(monkeypatch, text, expected):
    """Regresión: `sys.stdin` con búfer se tragaba el resto de la secuencia de la flecha."""
    import pty

    master, slave = pty.openpty()
    monkeypatch.setattr(sys, "stdin", os.fdopen(slave, "r", closefd=False))

    try:
        os.write(master, text + b"x")
        assert menu.read_key() == expected
    finally:
        os.close(master)
        os.close(slave)


def windows_console(monkeypatch, text):
    chars = iter(text)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getwch=lambda: next(chars)))


@pytest.mark.parametrize(
    ("text", "expected"),
    [("\xe0H", "UP"), ("\xe0P", "DOWN"), ("\x00H", "UP"), ("\x00P", "DOWN"), ("\xe0K", ""), ("\x00;", ""), ("a", "a")],
)
def test_read_key_reads_arrows_on_windows(monkeypatch, text, expected):
    windows_console(monkeypatch, text)
    assert menu.read_key() == expected


def test_read_key_ctrl_c_on_windows(monkeypatch):
    windows_console(monkeypatch, "\x03")

    with pytest.raises(KeyboardInterrupt):
        menu.read_key()


def test_without_ansi_support_windows_falls_back_to_commas(monkeypatch, lines):
    lines("1,3")
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(menu, "_enable_ansi", lambda: False)
    monkeypatch.setattr(menu, "read_key", lambda: "")
    assert menu.choose_many("Pick", OPTIONS) == ["a", "c"]
