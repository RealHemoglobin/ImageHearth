from aiohttp import web
from server import PromptServer
import comfy.model_management

# Debe coincidir con STATUS_NODE_VERSION de imagehearth_mcp.engine.config.
VERSION = 1


async def imagehearth_status(request):
    models = comfy.model_management.loaded_models()

    return web.json_response({
        "version": VERSION,
        "models_loaded": len(models),
        "loaded_models": [
            {
                "class": model.__class__.__name__,
            }
            for model in models
        ],
    })


# El nodo no aporta nodos de grafo: solo la ruta HTTP. ComfyUI exige que el
# módulo declare NODE_CLASS_MAPPINGS (aunque esté vacío) para darlo por cargado.
NODE_CLASS_MAPPINGS = {}

PromptServer.instance.routes.get("/imagehearth/status")(imagehearth_status)
