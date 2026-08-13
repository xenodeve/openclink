# Gemini CLI Setup

> **Note**: While OpenClink connects successfully to Gemini CLI, tool invocation is not working
> correctly yet. We'll update this guide once the integration is fully functional.

This guide explains how to configure PAL MCP Server to work with [Gemini CLI](https://github.com/google-gemini/gemini-cli).

## Prerequisites

- OpenClink installed and configured
- Gemini CLI installed
- At least one API key configured in your `.env` file

## Configuration

1. Edit `~/.gemini/settings.json` and add:

```json
{
  "mcpServers": {
    "openclink": {
      "command": "/path/to/openclink/openclink"
    }
  }
}
```

2. Replace `/path/to/openclink` with your actual OpenClink installation path (the folder name may still be `openclink`).

3. If the `openclink` wrapper script doesn't exist, create it:

```bash
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec .openclink_venv/bin/python server.py "$@"
```

Then make it executable: `chmod +x openclink`

4. Restart Gemini CLI.

All 15 OpenClink tools are now available in your Gemini CLI session.
