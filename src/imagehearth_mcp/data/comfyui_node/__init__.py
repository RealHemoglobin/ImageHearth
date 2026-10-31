from aiohttp import web
from server import PromptServer
import comfy.model_management


async def imageengine_status(request):
    models = comfy.model_management.loaded_models()

    return web.json_response({
        "models_loaded": len(models),
        "loaded_models": [
            {
                "class": model.__class__.__name__,
            }
            for model in models
        ],
    })


async def comfy_entrypoint():
    PromptServer.instance.routes.get(
        "/imageengine/status"
    )(imageengine_status)
