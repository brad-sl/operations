# Delegation Model Policy

**Date:** 2026-05-29  
**Owner:** Hermes Agent (main session)

## Default Models for Sub-Agents

To reduce cost while maintaining quality, sub-agents spawned via `delegate_task` should use the following models (via OpenRouter):

### Primary Default
- **Model**: `google/gemini-2.0-flash`
- **Use for**: Most tasks (coding, analysis, implementation, debugging, data work)

### Backup Model
- **Model**: `deepseek/deepseek-chat`
- **Use for**: When Gemini Flash is unavailable or for slightly more complex coding tasks

### High-Complexity Fallback
- **Model**: `xai/grok-4.3` (current main model)
- **Use only when**: The task requires strong reasoning, architecture decisions, or complex multi-step planning

## Guidelines

- Default to `gemini-2.0-flash` unless the task is explicitly marked as high-complexity.
- Use `deepseek/deepseek-chat` as a secondary option when needed.
- Reserve `grok-4.3` for tasks where cheaper models are likely to underperform.
- Always pass the model explicitly in `delegate_task` calls when deviating from the default.

## Example Delegation

```python
delegate_task(
    goal="...",
    role="leaf",
    model={"provider": "openrouter", "model": "google/gemini-2.0-flash"}
)
```

## Notes

- This policy was introduced after cost/performance comparison of sub-agent output.
- Gemini 2.0 Flash offers the best current balance of price and capability for agentic work.
- Review this policy periodically as new models are released.
## Current Implementation (May 2026)

Model changes were applied at the **profile level** in `~/.hermes/profiles/<name>/config.yaml`:

**Updated to Gemini 2.0 Flash + OpenRouter:**
- crypto-analyst, crypto-engineer, market-researcher, performance-analyst
- content-editor, seo-specialist, sem-specialist, ad-copywriter
- video-producer, visual-designer, publisher, crypto-monitor

**Kept on xAI (grok-4-1-fast-non-reasoning):**
- crypto-orchestrator, marketing-orchestrator, creative-director

This gives a good balance between cost and capability.
