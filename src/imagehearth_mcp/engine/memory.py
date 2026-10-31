"""Interfaz para liberar y recuperar la memoria que ocupan otros servidores."""

from abc import ABC, abstractmethod

from imagehearth_mcp.engine import config


class ProviderUnavailable(RuntimeError):
    """El servidor de modelos no responde."""


class MemoryProvider(ABC):
    name = ""

    @abstractmethod
    def loaded(self):
        """Modelos cargados en memoria. Lanza ProviderUnavailable si no responde."""

    @abstractmethod
    def unload(self, models):
        """Descarga los modelos indicados y espera a que la memoria quede libre."""

    @abstractmethod
    def restore(self, models):
        """Recarga los modelos; devuelve {"restored": [...], "failed": [...]}."""


class DisabledProvider(MemoryProvider):
    """`ollama_mode = "off"`: no se toca ningún modelo."""

    name = "none"

    def loaded(self):
        return []

    def unload(self, models):
        pass

    def restore(self, models):
        # Con modelos pendientes de una sesión anterior no se puede garantizar nada.
        return {"restored": [], "failed": [model["name"] for model in models]}


def get_provider():
    if config.OLLAMA_MODE == "off":
        return DisabledProvider()

    from imagehearth_mcp.engine.ollama_manager import OllamaProvider

    return OllamaProvider()
