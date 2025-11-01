# Adding Custom AI Models

How to add and configure custom AI models.

---

## Basic Setup

Edit `configs/default_config.json`:

```json
{
  "models": [
    {
      "name": "Your Model Name",
      "basemodel": "provider/model-id",
      "signature": "unique-identifier",
      "enabled": true
    }
  ]
}
```

---

## Examples

### OpenAI Models

```json
{
  "name": "GPT-4",
  "basemodel": "openai/gpt-4",
  "signature": "gpt-4",
  "enabled": true
}
```

### Anthropic Claude

```json
{
  "name": "Claude 3.7 Sonnet",
  "basemodel": "anthropic/claude-3.7-sonnet",
  "signature": "claude-3.7-sonnet",
  "enabled": true,
  "openai_base_url": "https://api.anthropic.com/v1",
  "openai_api_key": "your-anthropic-key"
}
```

### Via OpenRouter

```json
{
  "name": "DeepSeek",
  "basemodel": "deepseek/deepseek-chat",
  "signature": "deepseek",
  "enabled": true,
  "openai_base_url": "https://openrouter.ai/api/v1",
  "openai_api_key": "your-openrouter-key"
}
```

---

## Field Reference

See [docs/user-guide/configuration.md](../user-guide/configuration.md#model-configuration-fields) for complete field descriptions.
