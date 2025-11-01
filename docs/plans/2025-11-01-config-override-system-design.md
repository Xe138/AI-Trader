# Configuration Override System Design

**Date:** 2025-11-01
**Status:** Approved
**Context:** Enable per-deployment model configuration while maintaining sensible defaults

## Problem

Deployments need to customize model configurations without modifying the image's default config. Currently, the API looks for `configs/default_config.json` at startup, but volume mounts that include custom configs would overwrite the default config baked into the image.

## Solution Overview

Implement a layered configuration system where:
- Default config is baked into the Docker image
- User config is provided via volume mount in a separate directory
- Configs are merged at container startup (before API starts)
- Validation failures cause immediate container exit

## Architecture

### File Locations

- **Default config (in image):** `/app/configs/default_config.json`
- **User config (mounted):** `/app/user-configs/config.json`
- **Merged output:** `/tmp/runtime_config.json`

### Startup Sequence

1. **Entrypoint phase** (before uvicorn):
   - Load `configs/default_config.json` from image
   - Check if `user-configs/config.json` exists
   - If exists: perform root-level merge (custom sections override default sections)
   - Validate merged config structure
   - If validation fails: log detailed error and `exit 1`
   - Write merged config to `/tmp/runtime_config.json`
   - Export `CONFIG_PATH=/tmp/runtime_config.json`

2. **API initialization:**
   - Load pre-validated config from `$CONFIG_PATH`
   - No runtime config validation needed (already validated)

### Merge Behavior

**Root-level merge:** Custom config sections completely replace default sections.

```python
default = load_json("configs/default_config.json")
custom = load_json("user-configs/config.json") if exists else {}

merged = {**default}
for key in custom:
    merged[key] = custom[key]  # Override entire section
```

**Examples:**
- Custom has `models` array → entire models array replaced
- Custom has `agent_config` → entire agent_config replaced
- Custom missing `date_range` → default date_range used
- Custom has unknown keys → passed through (validated in next step)

### Validation Rules

**Structure validation:**
- Required top-level keys: `agent_type`, `models`, `agent_config`, `log_config`
- `date_range` is optional (can be overridden by API request params)
- `models` must be an array with at least one entry
- Each model must have: `name`, `basemodel`, `signature`, `enabled`

**Model validation:**
- At least one model must have `enabled: true`
- Model signatures must be unique
- No duplicate model names

**Date validation (if date_range present):**
- Dates match `YYYY-MM-DD` format
- `init_date` <= `end_date`
- Dates are not in the future

**Agent config validation:**
- `max_steps` > 0
- `max_retries` >= 0
- `initial_cash` > 0

### Error Handling

**Validation failure output:**
```
❌ CONFIG VALIDATION FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Error: Missing required field 'models'
Location: Root level
File: user-configs/config.json

Merged config written to: /tmp/runtime_config.json (for debugging)

Container will exit. Fix config and restart.
```

**Benefits of fail-fast approach:**
- No silent config errors during API calls
- Clear feedback on what's wrong
- Container restart loop until config is fixed
- Health checks fail immediately (container never reaches "running" state with bad config)

## Implementation Components

### New Files

**`tools/config_merger.py`**
```python
def load_config(path: str) -> dict:
    """Load and parse JSON with error handling"""

def merge_configs(default: dict, custom: dict) -> dict:
    """Root-level merge - custom sections override default"""

def validate_config(config: dict) -> None:
    """Validate structure, raise detailed exception on failure"""

def merge_and_validate() -> None:
    """Main entrypoint - load, merge, validate, write to /tmp"""
```

### Updated Files

**`entrypoint.sh`**
```bash
# After MCP service startup, before uvicorn
echo "🔧 Merging and validating configuration..."
python -c "from tools.config_merger import merge_and_validate; merge_and_validate()" || exit 1
export CONFIG_PATH=/tmp/runtime_config.json
echo "✅ Configuration validated"

exec uvicorn api.main:app ...
```

**`docker-compose.yml`**
```yaml
volumes:
  - ./data:/app/data
  - ./logs:/app/logs
  - ./configs:/app/user-configs  # User's config.json (not /app/configs!)
```

**`api/main.py`**
- Keep existing `CONFIG_PATH` env var support (already implemented)
- Remove any config validation from request handlers (now done at startup)

### Documentation Updates

- **`docs/DOCKER.md`** - Explain user-configs volume mount and config.json structure
- **`QUICK_START.md`** - Show minimal config.json example
- **`API_REFERENCE.md`** - Note that config errors fail at startup, not during API calls
- **`CLAUDE.md`** - Update configuration section with new merge behavior

## User Experience

### Minimal Custom Config Example

```json
{
  "models": [
    {
      "name": "my-gpt-4",
      "basemodel": "openai/gpt-4",
      "signature": "my-gpt-4",
      "enabled": true
    }
  ]
}
```

All other settings (`agent_config`, `log_config`, etc.) inherited from default.

### Complete Custom Config Example

```json
{
  "agent_type": "BaseAgent",
  "date_range": {
    "init_date": "2025-10-01",
    "end_date": "2025-10-31"
  },
  "models": [
    {
      "name": "claude-sonnet-4",
      "basemodel": "anthropic/claude-sonnet-4",
      "signature": "claude-sonnet-4",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 50,
    "max_retries": 5,
    "base_delay": 2.0,
    "initial_cash": 100000.0
  },
  "log_config": {
    "log_path": "./data/agent_data"
  }
}
```

All sections replaced, no inheritance from default.

## Backward Compatibility

**If no `user-configs/config.json` exists:**
- System uses `configs/default_config.json` as-is
- No merging needed
- Existing behavior preserved

**Breaking change:**
- Deployments currently mounting to `/app/configs` must update to `/app/user-configs`
- Migration: Update docker-compose.yml volume mount path

## Security Considerations

- Default config in image is read-only (immutable)
- User config directory is writable (mounted volume)
- Merged config in `/tmp` is ephemeral (recreated on restart)
- API keys in user config are not logged during validation errors

## Testing Strategy

**Unit tests (`tests/unit/test_config_merger.py`):**
- Merge behavior with various override combinations
- Validation catches all error conditions
- Error messages are clear and actionable

**Integration tests:**
- Container startup with valid user config
- Container startup with invalid user config (should exit 1)
- Container startup with no user config (uses default)
- API requests use merged config correctly

**Manual testing:**
- Deploy with minimal config.json (only models)
- Deploy with complete config.json (all sections)
- Deploy with invalid config.json (verify error output)
- Deploy with no config.json (verify default behavior)

## Future Enhancements

- Deep merge support (merge within sections, not just root-level)
- Config schema validation using JSON Schema
- Support for multiple config files (e.g., base + environment + deployment)
- Hot reload on config file changes (SIGHUP handler)
