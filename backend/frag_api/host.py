"""Installed, one-project Host. Program files and project files are never state storage."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def checked_paths(workspace: Path, state: Path, installation: Path) -> tuple[Path, Path]:
    for path in (workspace, state, installation):
        current = path.absolute()
        while current != current.parent:
            if current.is_symlink() or getattr(current.lstat() if current.exists() else None,
                                              "st_file_attributes", 0) & 0x400:
                raise ValueError("Host directories cannot contain links or reparse points.")
            current = current.parent
    root, data, program = workspace.resolve(strict=True), state.resolve(), installation.resolve(strict=True)
    if not root.is_dir() or any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
                              for a, b in ((data, root), (data, program), (root, program))):
        raise ValueError("Installation, project and state must be separate directories.")
    data.mkdir(parents=True, exist_ok=True)
    return root, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bridge-url", required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a nonprivileged loopback port.")
    root, state = checked_paths(args.workspace, args.state_dir, args.installation)
    # Set before importing main; installed Hosts never load a development .env.
    os.environ["FRAG_HOST_INSTALLED"] = "1"
    from frag_api.main import create_app
    from frag_api.providers.vscode import ModelBridge
    import uvicorn

    resources = args.installation / "resources"
    bridge = ModelBridge(args.bridge_url, os.environ.pop("FRAG_BRIDGE_KEY", ""))
    app = create_app(context_source_root=root, workspace_root=root, model_bridge=bridge,
        rag_index_path=state / "rag/index.sqlite3", rag_source_root=resources / "demo/rag",
        rag_eval_path=resources / "demo/rag/eval-cases.json", plugin_root=state / "plugins",
        runtime_path=state / "runtime.sqlite3", agent_host_enabled=True,
        review_assets=resources / "dist", review_help=resources / "review.md",
        review_origin=f"http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
