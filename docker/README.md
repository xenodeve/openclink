# OpenClink - Docker Setup

## Migration: upgrading from the `pal-mcp` Docker names

The Docker service, image, and named volume were renamed from the `pal-mcp` family
to `openclink` (service `pal-mcp` → `openclink`, volume `pal-mcp-config` →
`openclink-config`, image `pal-mcp-server:latest` → `openclink:latest`). Docker
Compose does **not** carry data over automatically when a named volume is renamed
— it will create a new, empty `openclink-config` volume, and your existing
`pal-mcp-config` volume stays on disk untouched but unused.

If you have existing configuration in `pal-mcp-config`, copy it into the new
volume before starting the renamed stack:

```bash
# Create the new volume and copy the old volume's contents into it
docker volume create openclink-config
docker run --rm \
  -v pal-mcp-config:/from \
  -v openclink-config:/to \
  alpine sh -c "cp -a /from/. /to/"
```

Then start the stack as usual (`docker-compose up -d`). If you skip this step,
the stack still starts fine — it just starts with default/empty configuration.
Nothing is deleted; your old `pal-mcp-config` volume remains on disk and can be
removed later with `docker volume rm pal-mcp-config` once you've confirmed the
new volume has what you need.

## Quick Start

### 1. Prerequisites

- Docker installed (Docker Compose optional)
- At least one API key (Gemini, OpenAI, xAI, etc.)

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your API keys (at least one required)
# Required: GEMINI_API_KEY or OPENAI_API_KEY or XAI_API_KEY
nano .env
```

### 3. Build Image

```bash
# Build the Docker image
docker build -t openclink:latest .

# Or use the build script (Bash)
chmod +x docker/scripts/build.sh
./docker/scripts/build.sh

# Build with PowerShell
docker/scripts/build.ps1

```

### 4. Usage Options

#### A. Direct Docker Run (Recommended for MCP)

```bash
# Run with environment file
docker run --rm -i --env-file .env \
  -v $(pwd)/logs:/app/logs \
  openclink:latest

# Run with inline environment variables
docker run --rm -i \
  -e GEMINI_API_KEY="your_key_here" \
  -e LOG_LEVEL=INFO \
  -v $(pwd)/logs:/app/logs \
  openclink:latest
```

#### B. Docker Compose (For Development/Monitoring)

```bash
# Deploy with Docker Compose
chmod +x docker/scripts/deploy.sh
./docker/scripts/deploy.sh

# Or use PowerShell script
docker/scripts/deploy.ps1

# Interactive stdio mode
docker-compose exec openclink python server.py
```

## Service Management

### Docker Commands

```bash
# View running containers
docker ps

# View logs from container
docker logs <container_id>

# Stop all openclink containers
docker stop $(docker ps -q --filter "ancestor=openclink:latest")

# Remove old containers and images
docker container prune
docker image prune
```

### Docker Compose Management (Optional)

```bash
# View logs
docker-compose logs -f openclink

# Check status
docker-compose ps

# Restart service
docker-compose restart openclink

# Stop services
docker-compose down

# Rebuild and update
docker-compose build --no-cache openclink
docker-compose up -d openclink
```

## Health Monitoring

The container includes health checks that verify:
- Server process is running
- Python modules can be imported
- Log directory is writable  
- API keys are configured

## Volumes and Persistent Data

The Docker setup includes persistent volumes to preserve data between container runs:

- **`./logs:/app/logs`** - Persistent log storage (local folder mount)
- **`openclink-config:/app/conf`** - Configuration persistence (named Docker volume)
- **`/etc/localtime:/etc/localtime:ro`** - Host timezone synchronization (read-only)

### How Persistent Volumes Work

The `openclink` service (used by `docker-compose.yml` and Docker Compose commands) mounts the named volume `openclink-config` persistently. All data placed in `/app/conf` inside the container is preserved between runs thanks to this Docker volume.

In the `docker-compose.yml` file, you will find:

```yaml
volumes:
  - ./logs:/app/logs
  - openclink-config:/app/conf
  - /etc/localtime:/etc/localtime:ro
```

and the named volume definition:

```yaml
volumes:
  openclink-config:
    driver: local
```

## Security

- Runs as non-root user `paluser`
- Read-only filesystem with tmpfs for temporary files
- No network ports exposed (stdio communication only)
- Secrets managed via environment variables

## Troubleshooting

### Container won't start

```bash
# Check if image exists
docker images openclink

# Test container interactively
docker run --rm -it --env-file .env openclink:latest bash

# Check environment variables
docker run --rm --env-file .env openclink:latest env | grep API

# Test with minimal configuration
docker run --rm -i -e GEMINI_API_KEY="test" openclink:latest python server.py
```

### MCP Connection Issues

```bash
# Test Docker connectivity
docker run --rm hello-world

# Verify container stdio
echo '{"jsonrpc": "2.0", "method": "ping"}' | docker run --rm -i --env-file .env openclink:latest python server.py

# Check Claude Desktop logs for connection errors
```

### API Key Problems

```bash
# Verify API keys are loaded
docker run --rm --env-file .env openclink:latest python -c "import os; print('GEMINI_API_KEY:', bool(os.getenv('GEMINI_API_KEY')))"

# Test API connectivity
docker run --rm --env-file .env openclink:latest python /usr/local/bin/healthcheck.py
```

### Permission Issues

```bash
# Fix log directory permissions (Linux/macOS)
sudo chown -R $USER:$USER logs/
chmod 755 logs/

# Windows: Run Docker Desktop as Administrator if needed
```

### Memory/Performance Issues

```bash
# Check container resource usage
docker stats

# Run with memory limits
docker run --rm -i --memory="512m" --env-file .env openclink:latest

# Monitor Docker logs
docker run --rm -i --env-file .env openclink:latest 2>&1 | tee docker.log
```

## MCP Integration (Claude Desktop)

### Recommended Configuration (docker run)

```json
{
  "servers": {
    "openclink-docker": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/absolute/path/to/openclink/.env",
        "-v",
        "/absolute/path/to/openclink/logs:/app/logs",
        "openclink:latest"
      ]
    }
  }
}
```

### Windows Example

```json
{
  "servers": {
    "openclink-docker": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "C:/Users/YourName/path/to/openclink/.env",
        "-v",
        "C:/Users/YourName/path/to/openclink/logs:/app/logs",
        "openclink:latest"
      ]
    }
  }
}
```

### Advanced Option: docker-compose run (uses compose configuration)

```json
{
  "servers": {
    "openclink-docker": {
      "command": "docker-compose",
      "args": [
        "-f",
        "/absolute/path/to/openclink/docker-compose.yml",
        "run",
        "--rm",
        "openclink"
      ]
    }
  }
}
```

### Environment File Template

Create a `.env` file with at least one API key:

```bash
# Required: At least one API key
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here

# Optional configuration
LOG_LEVEL=INFO
DEFAULT_MODEL=auto
DEFAULT_THINKING_MODE_THINKDEEP=high

# Optional API keys (leave empty if not used)
ANTHROPIC_API_KEY=
XAI_API_KEY=
DIAL_API_KEY=
OPENROUTER_API_KEY=
CUSTOM_API_URL=
```

## Quick Test & Validation

### 1. Test Docker Image

```bash
# Test container starts correctly
docker run --rm openclink:latest python --version

# Test health check
docker run --rm -e GEMINI_API_KEY="test" openclink:latest python /usr/local/bin/healthcheck.py
```

### 2. Test MCP Protocol

```bash
# Test basic MCP communication
echo '{"jsonrpc": "2.0", "method": "initialize", "params": {}}' | \
  docker run --rm -i --env-file .env openclink:latest python server.py
```

### 3. Validate Configuration

```bash
# Run validation script
python test_mcp_config.py

# Or validate JSON manually
python -m json.tool .vscode/mcp.json
```

## Available Tools

The OpenClink provides these tools when properly configured:

- **chat** - General AI conversation and collaboration
- **thinkdeep** - Multi-stage investigation and reasoning  
- **planner** - Interactive sequential planning
- **consensus** - Multi-model consensus workflow
- **codereview** - Comprehensive code review
- **debug** - Root cause analysis and debugging
- **analyze** - Code analysis and assessment
- **refactor** - Refactoring analysis and suggestions
- **secaudit** - Security audit workflow
- **testgen** - Test generation with edge cases
- **docgen** - Documentation generation
- **tracer** - Code tracing and dependency mapping
- **precommit** - Pre-commit validation workflow
- **listmodels** - Available AI models information
- **version** - Server version and configuration

## Performance Notes

- **Image size**: ~293MB optimized multi-stage build
- **Memory usage**: ~256MB base + model overhead
- **Startup time**: ~2-3 seconds for container initialization
- **API response**: Varies by model and complexity (1-30 seconds)

For production use, consider:
- Using specific API keys for rate limiting
- Monitoring container resource usage
- Setting up log rotation for persistent logs
- Using Docker health checks for reliability
