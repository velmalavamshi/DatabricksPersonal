# Collective Intelligence Skill (W4)

## Purpose
Provide cross-client benchmarks, pattern recognition, failure prediction,
and trend analysis. This skill replaces the W4 agent workspace — the Supervisor
loads these files into its context and responds directly (single LLM call).

## When This Skill Activates
Keywords: benchmark, patterns, prediction, competitive, cross-client, trend, forecast, intelligence, leaderboard

## Skill Files
- `benchmark_data.md` — Cross-client performance benchmarks by category
- `pattern_library.md` — Known patterns, anti-patterns, and best practices
- `prediction_models.md` — Failure prediction heuristics and risk scoring

## Response Format (when this skill is active)
1. Header: 🎯 W4 Collective Intelligence | Skill Mode
2. Identify sub-capability (Benchmark / Pattern / Prediction / Trend)
3. Apply relevant data from skill files
4. Deliver structured output with evidence
5. End with: 💬 Next Steps

## Quality Standards
- All benchmarks must cite the source category and sample size
- Patterns must include: name, description, symptoms, resolution
- Predictions must show confidence level and contributing factors
- Never present internal Hologic data as cross-client benchmarks
