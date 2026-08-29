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
OptionalCanvasId = Annotated[
    str | None,
    Field(
        min_length=32,
        max_length=32,
        pattern=ID_PATTERN,
        description="Existing canvas identifier; omit to create a new canvas",
    ),
]
Title = Annotated[str, Field(min_length=1, max_length=120, description="Short card title")]
Body = Annotated[str, Field(max_length=4_000, description="Card details")]
Kind = Annotated[str, Field(min_length=1, max_length=32, description="Freeform card category")]
Color = Annotated[
    str,
    Field(pattern=r"^#[0-9A-Fa-f]{6}$", description="Six-digit hexadecimal card color"),
]
Coordinate = Annotated[
    float | None,
    Field(ge=-100_000, le=100_000, description="Canvas coordinate; omit for automatic placement"),
]
NodeId = Annotated[
    str,
    Field(min_length=32, max_length=32, pattern=ID_PATTERN, description="Card identifier returned by add_node"),
]
OptionalTitle = Annotated[str | None, Field(max_length=120, description="Replacement card title")]
OptionalBody = Annotated[str | None, Field(max_length=4_000, description="Replacement card details")]
OptionalKind = Annotated[str | None, Field(max_length=32, description="Replacement card category")]
OptionalColor = Annotated[
    str | None,
    Field(pattern=r"^#[0-9A-Fa-f]{6}$", description="Replacement six-digit hexadecimal card color"),
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


def _validate_text(value: str, field: str, maximum: int, *, required: bool = False) -> str:
    cleaned = value.strip() if required else value
    if required and not cleaned:
        raise ValueError(f"{field} cannot be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def _validate_color(value: str) -> str:
    if len(value) != 7 or value[0] != "#" or any(character not in "0123456789abcdefABCDEF" for character in value[1:]):
        raise ValueError("Color must be a six-digit hexadecimal value")
    return value.upper()


def _validate_coordinate(value: float | None) -> float | None:
    if value is not None and not -100_000 <= value <= 100_000:
        raise ValueError("Coordinates must be between -100000 and 100000")
    return value


def _add_node(
    title: str,
    body: str = "",
    kind: str = "note",
    color: str = "#FFF1A8",
    x: float | None = None,
    y: float | None = None,
    canvas_id: str | None = None,
) -> dict[str, Any]:
    title = _validate_text(title, "Title", 120, required=True)
    body = _validate_text(body, "Body", 4_000)
    kind = _validate_text(kind, "Kind", 32, required=True)
    color = _validate_color(color)
    x = _validate_coordinate(x)
    y = _validate_coordinate(y)
    canvas_id = canvas_id or _create_canvas()["id"]
    _validate_id(canvas_id, "canvas")

    with _store_lock:
        canvas = _canvases.get(canvas_id)
        if canvas is None:
            raise KeyError(f"Canvas '{canvas_id}' was not found")
        if len(canvas["nodes"]) >= MAX_NODES:
            raise ValueError("Node limit reached")
        position = len(canvas["nodes"])
        node = {
            "id": _new_id(),
            "title": title,
            "body": body,
            "kind": kind,
            "color": color,
            "x": x if x is not None else 80 + (position % 4) * 280,
            "y": y if y is not None else 80 + (position // 4) * 190,
        }
        canvas["nodes"].append(node)
        canvas["revision"] += 1
        return {"canvas_id": canvas_id, "node": deepcopy(node), "revision": canvas["revision"]}


def _update_node(
    canvas_id: str,
    node_id: str,
    title: str | None = None,
    body: str | None = None,
    kind: str | None = None,
    color: str | None = None,
    x: float | None = None,
    y: float | None = None,
) -> dict[str, Any]:
    _validate_id(canvas_id, "canvas")
    _validate_id(node_id, "node")
    changes = {
        key: value
        for key, value in {
            "title": title,
            "body": body,
            "kind": kind,
            "color": color,
            "x": x,
            "y": y,
        }.items()
        if value is not None
    }
    if not changes:
        raise ValueError("At least one node field must be provided")
    if "title" in changes:
        changes["title"] = _validate_text(changes["title"], "Title", 120, required=True)
    if "body" in changes:
        changes["body"] = _validate_text(changes["body"], "Body", 4_000)
    if "kind" in changes:
        changes["kind"] = _validate_text(changes["kind"], "Kind", 32, required=True)
    if "color" in changes:
        changes["color"] = _validate_color(changes["color"])
    if "x" in changes:
        changes["x"] = _validate_coordinate(changes["x"])
    if "y" in changes:
        changes["y"] = _validate_coordinate(changes["y"])

    with _store_lock:
        canvas = _canvases.get(canvas_id)
        if canvas is None:
            raise KeyError(f"Canvas '{canvas_id}' was not found")
        node = next((candidate for candidate in canvas["nodes"] if candidate["id"] == node_id), None)
        if node is None:
            raise KeyError(f"Node '{node_id}' was not found")
        node.update(changes)
        canvas["revision"] += 1
        return {"canvas_id": canvas_id, "node": deepcopy(node), "revision": canvas["revision"]}


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


@server.tool(
    description="Add a positioned card to a canvas, creating the canvas when canvas_id is omitted.",
    annotations=ToolAnnotations(destructiveHint=False, readOnlyHint=False, idempotentHint=False, openWorldHint=False),
    structured_output=True,
)
def add_node(
    title: Title,
    body: Body = "",
    kind: Kind = "note",
    color: Color = "#FFF1A8",
    x: Coordinate = None,
    y: Coordinate = None,
    canvas_id: OptionalCanvasId = None,
) -> dict[str, Any]:
    """Add a card and return its canvas and node identifiers."""
    return _add_node(title, body, kind, color, x, y, canvas_id)


@server.tool(
    description="Change selected fields or the position of an existing card.",
    annotations=ToolAnnotations(destructiveHint=False, readOnlyHint=False, idempotentHint=True, openWorldHint=False),
    structured_output=True,
)
def update_node(
    canvas_id: CanvasId,
    node_id: NodeId,
    title: OptionalTitle = None,
    body: OptionalBody = None,
    kind: OptionalKind = None,
    color: OptionalColor = None,
    x: Coordinate = None,
    y: Coordinate = None,
) -> dict[str, Any]:
    """Patch a card without replacing omitted fields."""
    return _update_node(canvas_id, node_id, title, body, kind, color, x, y)


if __name__ == "__main__":
    server.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
