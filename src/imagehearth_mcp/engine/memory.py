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
    """`memory_mode` en `off` o `manual`: no se toca ningún modelo."""

    name = "none"

    def loaded(self):
        return []

    def unload(self, models):
        pass

    def restore(self, models):
        # Con modelos pendientes de una sesión anterior no se puede garantizar nada.
        return {"restored": [], "failed": [model["name"] for model in models]}


class CombinedProvider(MemoryProvider):
    """Reparte cada operación entre los proveedores según el modelo.

    Un proveedor que no responde no tiene nada cargado, salvo que queden modelos
    suyos por restaurar: entonces constan como fallidos y se conserva la protección.
    """

    name = "auto"

    def __init__(self, providers):
        self.providers = {provider.name: provider for provider in providers}

    def _by_provider(self, models):
        groups = {}

        for model in models:
            # Las sesiones anteriores a esta interfaz solo podían ser de Ollama.
            groups.setdefault(model.get("provider", "ollama"), []).append(model)

        return groups

    def loaded(self):
        found = []
        answered = False

        for provider in self.providers.values():
            try:
                found.extend(provider.loaded())
                answered = True
            except ProviderUnavailable:
                continue

        if not answered:
            raise ProviderUnavailable("No model server responds.")

        return found

    def unload(self, models):
        for name, group in self._by_provider(models).items():
            self.providers[name].unload(group)

    def restore(self, models):
        result = {"restored": [], "failed": []}

        for name, group in self._by_provider(models).items():
            provider = self.providers.get(name)

            if provider is None:
                result["failed"].extend(model["name"] for model in group)
                continue

            outcome = provider.restore(group)
            result["restored"].extend(outcome["restored"])
            result["failed"].extend(outcome["failed"])

        return result


def get_provider():
    if config.memory_mode() != "auto":
        return DisabledProvider()

    from imagehearth_mcp.engine.memory_servers import (
        LlamaCppProvider,
        LMStudioProvider,
        VllmProvider,
    )
    from imagehearth_mcp.engine.ollama_manager import OllamaProvider

    return CombinedProvider(
        [OllamaProvider(), LMStudioProvider(), LlamaCppProvider(), VllmProvider()]
    )


def describe():
    """Estado de cada servidor de modelos, para `get_engine_status`."""
    mode = config.memory_mode()

    if mode != "auto":
        return {"mode": mode, "servers": {}}

    servers = {}

    for name, provider in get_provider().providers.items():
        try:
            servers[name] = {
                "status": "running",
                "loaded_models": [model["name"] for model in provider.loaded()],
            }
        except ProviderUnavailable:
            servers[name] = {"status": "stopped", "loaded_models": []}

    return {"mode": mode, "servers": servers}
