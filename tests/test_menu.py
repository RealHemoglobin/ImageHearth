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


def test_choose_many_enter_accepts_all():
    assert menu.choose_many("Pick", OPTIONS, reader=keys("\r")) == ["a", "b", "c"]


def test_choose_many_numbers_and_retry(capsys):
    assert menu.choose_many("Pick", OPTIONS, reader=keys("3,1\r")) == ["a", "c"]
    assert menu.choose_many("Pick", OPTIONS, reader=keys("7\rx\r2\r")) == ["b"]
    assert "separated by commas" in capsys.readouterr().out


def test_choose_many_zero_goes_back():
    assert menu.choose_many("Pick", OPTIONS, reader=keys("0\r")) is BACK


def test_choose_many_ctrl_c_raises():
    with pytest.raises(KeyboardInterrupt):
        menu.choose_many("Pick", OPTIONS, reader=keys("\x03"))


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


def test_line_mode_choose_many(lines):
    lines("")
    assert menu.choose_many("Pick", OPTIONS) == ["a", "b", "c"]
    lines("1, 3")
    assert menu.choose_many("Pick", OPTIONS) == ["a", "c"]
    lines("0")
    assert menu.choose_many("Pick", OPTIONS) is BACK


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

        def read(self, count):
            if failure:
                raise failure

            return "5"

    monkeypatch.setitem(sys.modules, "termios", fake)
    monkeypatch.setitem(sys.modules, "tty", fake_tty)
    monkeypatch.setattr(sys, "stdin", Stdin())

    if failure:
        with pytest.raises(failure):
            menu.read_key()
    else:
        assert menu.read_key() == "5"

    assert fake.calls == ["get", "cbreak", ("set", ["saved"])]
