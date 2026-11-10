# Value Discovery Skill (W2)

## Purpose
Provide AI maturity assessments, use case scoring, and client readiness reports.
This skill replaces the W2 agent workspace — the Supervisor loads these files
into its own context and responds directly (single LLM call).

## When This Skill Activates
Keywords: assessment, use cases, client, scanning, maturity, ROI, readiness

## Skill Files
- `assessment_framework.md` — 5-level maturity model + scoring rubric
- `use_case_scoring.md` — Use case evaluation criteria + prioritization matrix
- `client_report.md` — Report template + section structure

## Response Format (when this skill is active)
1. Header: 🎯 W2 Value Discovery | Skill Mode
2. Identify which sub-capability applies (Assessment / Scoring / Report)
3. Apply the relevant framework from skill files
4. Deliver structured output using the templates
5. End with: 💬 Next Steps

## Quality Standards
- All scores must reference the rubric (no hallucinated criteria)
- Maturity levels must use the 5-level framework exactly
- ROI estimates must show assumptions explicitly
- Reports must follow the section template in client_report.md
