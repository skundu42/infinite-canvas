# Infinite Canvas

A small, live spatial board for MCP. Models and browser users work on the same positioned cards and connections without translating the board into Mermaid source.

## Run locally

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open:

- Browser canvas: <http://localhost:8000>
- MCP endpoint: <http://localhost:8000/mcp>
- Inspector with `DEBUG=1`: <http://localhost:8000/inspector>

`HOST` and `PORT` override the default `0.0.0.0:8000` listener.

## Tools

| Tool | Purpose |
| --- | --- |
| `get_canvas` | Read a canvas by ID. |
| `add_node` | Add a card, creating a canvas when `canvas_id` is omitted. |
| `update_node` | Change selected card fields or position. |
| `connect_nodes` | Add a labeled, directed connection. |
| `export_canvas` | Export editable JSON or standalone SVG. |

Start a model-created board by calling `add_node` without `canvas_id`. Its result contains the generated canvas ID; open the matching browser board at `/?canvas=<canvas_id>` and keep passing that ID to later tool calls.

The browser supports card creation and editing, dragging, keyboard movement, connecting, pan/zoom, link sharing, and JSON/SVG downloads. It checks for model changes once per second and pauses polling during active edits.

## Development

```bash
python -m unittest -v
```

State is intentionally process-local and resets when the server restarts. Canvas IDs isolate boards within one process, but this template does not provide authentication, durable storage, deletion, or multi-worker synchronization.
