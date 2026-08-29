"""Infinite Canvas MCP server."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from functools import wraps
from html import escape
from pathlib import Path
from threading import Lock
from textwrap import wrap
from typing import Annotated, Any, Awaitable, Callable, Literal
from uuid import uuid4

from mcp.types import ToolAnnotations
from mcp_use.server import MCPServer
from mcp_use.server.runner import ServerRunner
from pydantic import Field
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response


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
Label = Annotated[str, Field(max_length=80, description="Optional connection label")]
ExportFormat = Annotated[
    Literal["json", "svg"],
    Field(description="Editable JSON or standalone SVG"),
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
    if not isinstance(value, str) or len(value) != 32 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"Invalid {kind} ID")


def _validate_text(value: str, field: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    cleaned = value.strip() if required else value
    if required and not cleaned:
        raise ValueError(f"{field} cannot be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return cleaned


def _validate_color(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or value[0] != "#"
        or any(character not in "0123456789abcdefABCDEF" for character in value[1:])
    ):
        raise ValueError("Color must be a six-digit hexadecimal value")
    return value.upper()


def _validate_coordinate(value: float | None) -> float | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError("Coordinates must be numbers")
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


def _connect_nodes(canvas_id: str, source_id: str, target_id: str, label: str = "") -> dict[str, Any]:
    _validate_id(canvas_id, "canvas")
    _validate_id(source_id, "source node")
    _validate_id(target_id, "target node")
    label = _validate_text(label, "Label", 80)
    if source_id == target_id:
        raise ValueError("A node cannot connect to itself")

    with _store_lock:
        canvas = _canvases.get(canvas_id)
        if canvas is None:
            raise KeyError(f"Canvas '{canvas_id}' was not found")
        node_ids = {node["id"] for node in canvas["nodes"]}
        missing = [node_id for node_id in (source_id, target_id) if node_id not in node_ids]
        if missing:
            raise KeyError(f"Node '{missing[0]}' was not found")
        duplicate = next(
            (
                connection
                for connection in canvas["connections"]
                if connection["source"] == source_id
                and connection["target"] == target_id
                and connection["label"] == label
            ),
            None,
        )
        if duplicate is not None:
            return {"canvas_id": canvas_id, "connection": deepcopy(duplicate), "revision": canvas["revision"]}
        if len(canvas["connections"]) >= MAX_CONNECTIONS:
            raise ValueError("Connection limit reached")
        connection = {"id": _new_id(), "source": source_id, "target": target_id, "label": label}
        canvas["connections"].append(connection)
        canvas["revision"] += 1
        return {"canvas_id": canvas_id, "connection": deepcopy(connection), "revision": canvas["revision"]}


def _export_canvas(canvas_id: str, output_format: str = "svg") -> dict[str, str]:
    canvas = _get_canvas(canvas_id)
    if output_format == "json":
        content = json.dumps(canvas, ensure_ascii=False, indent=2)
        mime_type = "application/json"
    elif output_format == "svg":
        content = _canvas_to_svg(canvas)
        mime_type = "image/svg+xml"
    else:
        raise ValueError("Format must be 'json' or 'svg'")
    return {
        "format": output_format,
        "mime_type": mime_type,
        "filename": f"infinite-canvas-{canvas_id[:8]}.{output_format}",
        "content": content,
    }


def _canvas_to_svg(canvas: Canvas) -> str:
    node_width, node_height, margin = 240, 132, 80
    nodes = canvas["nodes"]
    if nodes:
        min_x = min(node["x"] for node in nodes) - margin
        min_y = min(node["y"] for node in nodes) - margin
        max_x = max(node["x"] for node in nodes) + node_width + margin
        max_y = max(node["y"] for node in nodes) + node_height + margin
    else:
        min_x, min_y, max_x, max_y = 0, 0, 800, 600
    width, height = max_x - min_x, max_y - min_y
    by_id = {node["id"]: node for node in nodes}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:g} {min_y:g} {width:g} {height:g}" role="img" aria-label="Infinite Canvas export">',
        "<defs>",
        '<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#B8C7D4"/></pattern>',
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#F06449"/></marker>',
        '<style>.edge{stroke:#F06449;stroke-width:2.5;fill:none}.label{font:12px ui-monospace,monospace;fill:#455565}.kind{font:700 10px ui-monospace,monospace;letter-spacing:1.2px;fill:#455565}.title{font:700 18px system-ui,sans-serif;fill:#14222E}.body{font:13px system-ui,sans-serif;fill:#334654}</style>',
        "</defs>",
        f'<rect x="{min_x:g}" y="{min_y:g}" width="{width:g}" height="{height:g}" fill="#EAF1F7"/>',
        f'<rect x="{min_x:g}" y="{min_y:g}" width="{width:g}" height="{height:g}" fill="url(#grid)"/>',
    ]
    for connection in canvas["connections"]:
        source, target = by_id[connection["source"]], by_id[connection["target"]]
        x1, y1 = source["x"] + node_width / 2, source["y"] + node_height / 2
        x2, y2 = target["x"] + node_width / 2, target["y"] + node_height / 2
        parts.append(f'<path class="edge" d="M {x1:g} {y1:g} L {x2:g} {y2:g}" marker-end="url(#arrow)"/>')
        if connection["label"]:
            parts.append(
                f'<text class="label" x="{(x1 + x2) / 2:g}" y="{(y1 + y2) / 2 - 8:g}" text-anchor="middle">{escape(connection["label"])}</text>'
            )
    for node in nodes:
        x, y = node["x"], node["y"]
        parts.extend(
            [
                f'<g transform="translate({x:g} {y:g})">',
                f'<rect width="{node_width}" height="{node_height}" rx="12" fill="{node["color"]}" stroke="#7A8C9A"/>',
                f'<text class="kind" x="18" y="25">{escape(node["kind"].upper())}</text>',
                f'<text class="title" x="18" y="52">{escape(node["title"])}</text>',
            ]
        )
        for index, line in enumerate(wrap(node["body"], width=34)[:3]):
            parts.append(f'<text class="body" x="18" y="{78 + index * 18}">{escape(line)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


server = MCPServer(
    name="infinite-canvas",
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


@server.tool(
    description="Create a labeled, directed connection between two cards.",
    annotations=ToolAnnotations(destructiveHint=False, readOnlyHint=False, idempotentHint=True, openWorldHint=False),
    structured_output=True,
)
def connect_nodes(
    canvas_id: CanvasId,
    source_id: Annotated[str, Field(min_length=32, max_length=32, pattern=ID_PATTERN, description="Source card ID")],
    target_id: Annotated[str, Field(min_length=32, max_length=32, pattern=ID_PATTERN, description="Target card ID")],
    label: Label = "",
) -> dict[str, Any]:
    """Connect two cards, returning an existing exact duplicate unchanged."""
    return _connect_nodes(canvas_id, source_id, target_id, label)


@server.tool(
    description="Export a canvas as editable JSON or a standalone SVG that preserves card positions.",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    structured_output=True,
)
def export_canvas(canvas_id: CanvasId, format: ExportFormat = "svg") -> dict[str, str]:
    """Return a portable representation of the canvas."""
    return _export_canvas(canvas_id, format)


Handler = Callable[[Request], Awaitable[Response]]
INDEX_PATH = Path(__file__).with_name("public") / "index.html"
DEMO_PATH = Path(__file__).with_name("public") / "demo.html"


def _api_route(path: str, methods: list[str]) -> Callable[[Handler], Handler]:
    def decorate(handler: Handler) -> Handler:
        @wraps(handler)
        async def safe_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except KeyError as error:
                return JSONResponse({"error": error.args[0]}, status_code=404)
            except ValueError as error:
                return JSONResponse({"error": str(error)}, status_code=400)

        server.custom_route(path, methods=methods)(safe_handler)
        return safe_handler

    return decorate


async def _json_body(request: Request, allowed: set[str], required: set[str] = frozenset()) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as error:
        raise ValueError("Request body must be valid JSON") from error
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    unknown = set(body) - allowed
    missing = required - set(body)
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"Missing fields: {', '.join(sorted(missing))}")
    return body


@_api_route("/", ["GET"])
async def browser_canvas(_: Request) -> Response:
    return FileResponse(INDEX_PATH)


@_api_route("/api/canvases", ["POST"])
async def api_create_canvas(_: Request) -> Response:
    return JSONResponse(_create_canvas(), status_code=201)


@_api_route("/api/canvases/{canvas_id}", ["GET"])
async def api_get_canvas(request: Request) -> Response:
    return JSONResponse(_get_canvas(request.path_params["canvas_id"]))


@_api_route("/api/canvases/{canvas_id}/nodes", ["POST"])
async def api_add_node(request: Request) -> Response:
    body = await _json_body(request, {"title", "body", "kind", "color", "x", "y"}, {"title"})
    return JSONResponse(_add_node(canvas_id=request.path_params["canvas_id"], **body), status_code=201)


@_api_route("/api/canvases/{canvas_id}/nodes/{node_id}", ["PATCH"])
async def api_update_node(request: Request) -> Response:
    body = await _json_body(request, {"title", "body", "kind", "color", "x", "y"})
    return JSONResponse(_update_node(request.path_params["canvas_id"], request.path_params["node_id"], **body))


@_api_route("/api/canvases/{canvas_id}/connections", ["POST"])
async def api_connect_nodes(request: Request) -> Response:
    body = await _json_body(request, {"source_id", "target_id", "label"}, {"source_id", "target_id"})
    return JSONResponse(_connect_nodes(canvas_id=request.path_params["canvas_id"], **body), status_code=201)


@_api_route("/api/canvases/{canvas_id}/export", ["GET"])
async def api_export_canvas(request: Request) -> Response:
    exported = _export_canvas(request.path_params["canvas_id"], request.query_params.get("format", "svg"))
    return Response(
        exported["content"],
        media_type=exported["mime_type"],
        headers={"Content-Disposition": f'attachment; filename="{exported["filename"]}"'},
    )


class BrowserDemoPage:
    """Serve a human landing page without intercepting MCP protocol requests."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        headers = dict(scope.get("headers", []))
        accepts_html = b"text/html" in headers.get(b"accept", b"")
        is_browser_get = scope.get("method") in {"GET", "HEAD"} and accepts_html
        if scope.get("type") == "http" and scope.get("path") == "/mcp" and is_browser_get:
            await FileResponse(DEMO_PATH)(scope, receive, send)
            return
        await self.app(scope, receive, send)


application = BrowserDemoPage(server.streamable_http_app())


class CanvasServerRunner(ServerRunner):
    async def run_streamable_http_async(
        self, host: str = "127.0.0.1", port: int = 8000, reload: bool = False
    ) -> None:
        await self.serve_starlette_app(application, host, port, "streamable-http", reload)


if __name__ == "__main__":
    # ponytail: MCPServer.run() in 1.7.0 wraps the SDK's internal tool-cache lookup;
    # use its ASGI runner directly until that middleware bug is fixed upstream.
    CanvasServerRunner(server).run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
