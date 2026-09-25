"""The shared layer under the CLI, the MCP server and the HTTP API.

Each front end parses its own input and formats its own output; everything
else (which providers exist and how to build them, which tasks a run covers,
how a run is created and executed, how results are read back) lives here, so
the three behave the same way.
"""
