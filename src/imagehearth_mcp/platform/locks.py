import time
from contextlib import contextmanager

from filelock import FileLock, Timeout


def _lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(path)


def acquire(path, timeout, on_wait=None, poll=0.2):
    """Bloqueo entre procesos; el sistema lo libera si el proceso muere.

    Devuelve el objeto a liberar. Lanza TimeoutError si no se obtiene.
    """
    lock = _lock(path)
    deadline = time.monotonic() + timeout
    announced = False

    while True:
        try:
            lock.acquire(timeout=0)
            return lock
        except Timeout:
            if time.monotonic() >= deadline:
                raise TimeoutError(str(path)) from None

        if on_wait and not announced:
            on_wait()
            announced = True

        time.sleep(poll)


@contextmanager
def held(path, timeout, on_wait=None):
    lock = acquire(path, timeout, on_wait)

    try:
        yield
    finally:
        lock.release()


def is_locked(path):
    lock = _lock(path)

    try:
        lock.acquire(timeout=0)
    except Timeout:
        return True

    lock.release()
    return False
