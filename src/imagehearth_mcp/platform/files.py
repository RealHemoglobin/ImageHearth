import os
import time

REPLACE_ATTEMPTS = 6
REPLACE_DELAY = 0.05


def replace(source, destination, attempts=REPLACE_ATTEMPTS, delay=REPLACE_DELAY):
    """`os.replace` que reintenta ante bloqueos transitorios (antivirus, indexador)."""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise

            time.sleep(delay * (attempt + 1))
