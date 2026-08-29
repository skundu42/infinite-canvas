"""nfinite Canvas MCP server."""

from __future__ import annotations

import os

from mcp_use.server import MCPServer


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
