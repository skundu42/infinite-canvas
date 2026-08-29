"""nfinite Canvas MCP server."""

from __future__ import annotations

import os
from copy import deepcopy
from threading import Lock
from typing import Annotated, Any
from uuid import uuid4

from mcp.types import ToolAnnotations
from mcp_use.server import MCPServer
from pydantic import Field


Canvas = dict[str, Any]
MAX_CANVASES = 1_000
MAX_NODES = 500
MAX_CONNECTIONS = 2_000
ID_PATTERN = r"^[0-9a-f]{32}$"
CanvasId = Annotated[
    str,
    Field(
        min_length=32,
        max_length=32,
        pattern=ID_PATTERN,
        description="Canvas identifier returned by add_node or the browser editor",
    ),
]

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
    _validate_id(canvas_id, "canvas")
    with _store_lock:
        canvas = _canvases.get(canvas_id)
        if canvas is None:
            raise KeyError(f"Canvas '{canvas_id}' was not found")
        return deepcopy(canvas)


def _validate_id(value: str, kind: str) -> None:
    if len(value) != 32 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"Invalid {kind} ID")


server = MCPServer(
    name="nfinite-canvas",
    version="0.1.0",
    instructions="Build and refine freeform boards made of positioned cards and connections.",
    debug=os.getenv("DEBUG", "0") == "1",
)


@server.tool(
    description="Read every positioned card and connection from a canvas.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    structured_output=True,
)
def get_canvas(canvas_id: CanvasId) -> Canvas:
    """Return the current canvas state."""
    return _get_canvas(canvas_id)


if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
