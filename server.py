"""nfinite Canvas MCP server."""

from __future__ import annotations

import os
from copy import deepcopy
from threading import Lock
from typing import Any
from uuid import uuid4

from mcp_use.server import MCPServer


Canvas = dict[str, Any]
MAX_CANVASES = 1_000
MAX_NODES = 500
MAX_CONNECTIONS = 2_000

# ponytail: process-local state and one lock suit this template; use durable storage
# and per-canvas locks when persistence or multi-worker throughput matters.
_canvases: dict[str, Canvas] = {}
_store_lock = Lock()


def _new_id() -> str:
    return uuid4().hex


def _create_canvas() -> Canvas:
    with _store_lock:
        if len(_canvases) >= MAX_CANVASES:
            raise ValueError("Canvas limit reached")
        canvas: Canvas = {"id": _new_id(), "revision": 0, "nodes": [], "connections": []}
        _canvases[canvas["id"]] = canvas
        return deepcopy(canvas)


def _get_canvas(canvas_id: str) -> Canvas:
    with _store_lock:
        canvas = _canvases.get(canvas_id)
        if canvas is None:
            raise KeyError(f"Canvas '{canvas_id}' was not found")
        return deepcopy(canvas)


server = MCPServer(
    name="nfinite-canvas",
    version="0.1.0",
    instructions="Build and refine freeform boards made of positioned cards and connections.",
    debug=os.getenv("DEBUG", "0") == "1",
)


if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
