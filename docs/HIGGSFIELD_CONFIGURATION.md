# Higgsfield Studio Configuration

All configuration lives in `config.json` at the project root, under the `higgsfield` key.

## Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable/disable the Higgsfield Studio module |
| `api_key` | string | `""` | Higgsfield API key for video generation |
| `api_url` | string | `"https://api.higgsfield.ai/v1"` | Higgsfield API base URL |
| `default_model` | string | `""` | Default video generation model. Empty = auto-select based on quality mode |
| `default_quality` | string | `"quality"` | Default quality mode: `budget`, `balanced`, `quality`, `cinema` |
| `default_aspect_ratio` | string | `"16:9"` | Default aspect ratio for generated videos |
| `default_resolution` | string | `"1080p"` | Default output resolution |
| `max_parallel_jobs` | int | `2` | Maximum simultaneous generation jobs |
| `max_regeneration_attempts` | int | `3` | How many times to retry a shot that fails QC |
| `qc_threshold` | int | `75` | Quality score threshold for auto-approval (0-100) |
| `budget_limit` | float | `50.0` | Maximum spend per production in USD. `null` for no limit |
| `dry_run` | bool | `false` | Simulate generation without real API calls |
| `cost_rates` | object | `{}` | Custom per-model cost rates (see below) |

## Example Configuration

```json
{
  "higgsfield": {
    "enabled": true,
    "api_key": "hf_abc123...",
    "api_url": "https://api.higgsfield.ai/v1",
    "default_model": "",
    "default_quality": "quality",
    "default_aspect_ratio": "16:9",
    "default_resolution": "1080p",
    "max_parallel_jobs": 2,
    "max_regeneration_attempts": 3,
    "qc_threshold": 75,
    "budget_limit": 50.0,
    "dry_run": false,
    "cost_rates": {}
  }
}
```

## Per-Project Overrides

When creating a production (via API or UI), most settings can be overridden per-project:

```json
{
  "topic": "The rise and fall of the Roman Empire",
  "genre": "history",
  "quality": "cinema",
  "budget_limit": 100.0,
  "dry_run": false,
  "director_mode": "director",
  "production_mode": "full",
  "target_duration_min": 20.0,
  "language": "es",
  "narrator_voice": "es-ES-AlvaroNeural"
}
```

## Environment Variables

No environment variables are required. All configuration is in `config.json`.

## Cost Rates

Custom per-model pricing can be set in `cost_rates`. Keys are model IDs, values are cost per second of generated video in USD:

```json
{
  "higgsfield": {
    "cost_rates": {
      "model-standard-v1": 0.05,
      "model-premium-v2": 0.12
    }
  }
}
```

If no custom rate is set, the provider's built-in `estimated_cost_per_second` from its model capabilities is used.

## Quality Mode Effects

| Mode | QC Threshold | Model Preference | Regeneration Tolerance |
|------|-------------|------------------|----------------------|
| `budget` | 50 | Fastest/cheapest available | Low (fewer retries) |
| `balanced` | 65 | Mid-tier models | Medium |
| `quality` | 75 | High-capability models | High |
| `cinema` | 85 | Best available models | Maximum (uses all retry attempts) |
