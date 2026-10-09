"""Owned local evidence backend. No model configuration or bridge."""
import argparse
import os
from pathlib import Path
import uvicorn
from dotenv import load_dotenv

def checked_paths(workspace, state, installation):
    for path in (workspace, state, installation):
        current = path.absolute()
        while current != current.parent:
            if current.is_symlink() or getattr(current.lstat() if current.exists() else None, "st_file_attributes", 0) & 0x400:
                raise ValueError("Host directories cannot contain links or reparse points.")
            current = current.parent
    root, data, program = workspace.resolve(strict=True), state.resolve(), installation.resolve(strict=True)
    if not root.is_dir() or any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for a,b in ((data,root),(data,program),(root,program))):
        raise ValueError("Installation, project and state must be separate directories.")
    data.mkdir(parents=True, exist_ok=True)
    return root, data

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "state-dir", "installation"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a nonprivileged loopback port.")
    _, state = checked_paths(args.workspace, args.state_dir, args.installation)
    # FC credentials only; no workspace or model configuration is loaded.
    load_dotenv(state / "fc.env", override=False)
    from frag_api.main import create_app
    secret = os.environ.pop("FRAG_EXTENSION_TOKEN", "")
    app = create_app(state, secret)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="critical")

if __name__ == "__main__":
    main()
