from mcp import types
from mcp.server.fastmcp import FastMCP

server = FastMCP("CodeCraft MCP test server")


@server.tool(
    annotations=types.ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def add(a: int, b: int) -> dict[str, int]:
    """Add two integers."""
    return {"sum": a + b}


@server.tool(
    annotations=types.ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
    )
)
def echo(text: str) -> str:
    """Echo text from the test server."""
    return text


if __name__ == "__main__":
    server.run(transport="stdio")
