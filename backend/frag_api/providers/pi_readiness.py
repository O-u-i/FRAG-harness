"""User-operated readiness check: booleans and safe codes, never a model request."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from frag_api.providers.llm import LlmSettings
from frag_api.providers.pi_integrity import adapter_binding
from frag_api.providers.pi_process import ENVIRONMENT_NAMES, WORKER_ROOT, supported_model


def readiness() -> dict:
    settings = LlmSettings.from_environment()
    stages = (settings.context, settings.inference, settings.research)
    result = {"nodePresent": bool(shutil.which("node")), "packageVerified": False,
              "keyPresent": bool(os.environ.get("OPENAI_API_KEY")),
              "piEnabledForAllStages": all(stage is not None and stage.provider == "openai" and stage.adapter == "pi" for stage in stages),
              "modelsSupported": all(stage is not None and supported_model(stage.model) for stage in stages),
              "stagesReady": all(stage is not None and stage.ready for stage in stages),
              "ready": False, "code": "PI_NOT_READY"}
    try:
        adapter_binding()
        node = shutil.which("node")
        if node:
            child = subprocess.run([str(Path(node).resolve()), str(WORKER_ROOT / "verify-package.mjs")],
                cwd=WORKER_ROOT, env={name: os.environ[name] for name in ENVIRONMENT_NAMES if name in os.environ},
                shell=False, capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            result["packageVerified"] = (child.returncode == 0 and len(child.stdout) <= 4096
                and json.loads(child.stdout).get("status") == "PASS")
    except Exception:
        result["packageVerified"] = False
    result["ready"] = all(value for key, value in result.items() if key not in {"code", "ready"})
    result["code"] = "PI_READY" if result["ready"] else "PI_NOT_READY"
    return result


def main() -> int:
    try:
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        result = readiness()
    except Exception:
        result = {"ready": False, "code": "INVALID_PROVIDER_CONFIGURATION"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
