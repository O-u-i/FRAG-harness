from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/plugins")
def plugins(request: Request) -> dict:
    installed = request.app.state.plugin
    return {
        "protocolVersion": 1,
        "error": "Installed plugin failed validation." if request.app.state.plugin_error else None,
        "plugins": [{
            "id": "finance-core",
            "name": "Finance Core",
            "installed": installed is not None,
            "version": installed.version if installed else None,
            "uiUrl": installed.ui_url if installed else None,
        }],
    }
