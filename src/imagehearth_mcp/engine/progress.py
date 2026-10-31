"""Etapa de la generación en curso y su cancelación, sin depender de MCP.

El servidor crea un `Tracker` y lo instala con `tracking`; el contexto viaja al
hilo de trabajo con `asyncio.to_thread`. Sin tracker, estas funciones no hacen nada.
"""

import threading
from contextlib import contextmanager
from contextvars import ContextVar

_current = ContextVar("imagehearth_progress", default=None)


class GenerationCancelled(Exception):
    """El cliente ha cancelado la petición."""


class Tracker:
    def __init__(self):
        self.stage = "Waiting for a generation turn"
        self.cancelled = threading.Event()


@contextmanager
def tracking(tracker):
    token = _current.set(tracker)

    try:
        yield tracker
    finally:
        _current.reset(token)


def stage(message):
    tracker = _current.get()

    if tracker is not None:
        tracker.stage = message


def raise_if_cancelled():
    tracker = _current.get()

    if tracker is not None and tracker.cancelled.is_set():
        raise GenerationCancelled("The client cancelled the generation.")
