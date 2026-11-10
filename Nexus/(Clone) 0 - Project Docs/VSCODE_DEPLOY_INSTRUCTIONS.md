# VS Code → NEXUS: Deploy Claude Code Slash Commands (Option C)

**Date:** 2026-08-04  
**Status:** Deployed & tested  
**Architecture:** Claude Code (thin client) → Databricks CLI → FMAPI (`databricks-claude-sonnet-4-6`) → NEXUS 134 agents

---

## Quick Deploy (Copy-Paste into VS Code Terminal)

```bash
# ══════════════════════════════════════════════════════════════════════
# PASTE THIS ENTIRE BLOCK INTO YOUR VS CODE TERMINAL
# Prerequisites: Databricks CLI installed + DEV profile configured
# ══════════════════════════════════════════════════════════════════════

# Step 1: Create directory structure
mkdir -p .claude/commands

# Step 2: Export from Databricks workspace
WS_BASE="/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Project Docs/vscode_claude_code"

databricks workspace export "$WS_BASE/CLAUDE.md" ./CLAUDE.md --profile DEV --overwrite
databricks workspace export "$WS_BASE/commands/nexus.md" ./.claude/commands/nexus.md --profile DEV --overwrite
databricks workspace export "$WS_BASE/commands/nexus-qlik.md" ./.claude/commands/nexus-qlik.md --profile DEV --overwrite
databricks workspace export "$WS_BASE/commands/nexus-agent.md" ./.claude/commands/nexus-agent.md --profile DEV --overwrite
databricks workspace export "$WS_BASE/commands/nexus-status.md" ./.claude/commands/nexus-status.md --profile DEV --overwrite

# Step 3: Verify
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ NEXUS Claude Code Integration Deployed!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Commands available:"
echo "  /nexus <request>          → Route through 134-agent Meta Supervisor"
echo "  /nexus-qlik <step>        → Qlik Migration (Agent 88)"
echo "  /nexus-agent <id> <req>   → Direct agent call by ID"
echo "  /nexus-status             → Platform health check"
echo ""
echo "Cluster: Phoenix Shared Compute (0925-054849-fb85h9tq)"
echo "LLM: databricks-claude-sonnet-4-6 via FMAPI"
echo "═══════════════════════════════════════════════════════════"
```

---

## What Gets Deployed

| File | Local Path | Purpose |
|------|------------|----------|
| `CLAUDE.md` | Project root | System prompt — tells Claude Code to route through NEXUS |
| `nexus.md` | `.claude/commands/` | `/nexus` — Route any request through Meta Supervisor |
| `nexus-qlik.md` | `.claude/commands/` | `/nexus-qlik` — Qlik Migration (Agent 88→89-96) |
| `nexus-agent.md` | `.claude/commands/` | `/nexus-agent` — Direct agent call by ID |
| `nexus-status.md` | `.claude/commands/` | `/nexus-status` — Platform health check |

---

## Usage Examples

```
/nexus "What are the top 5 cost drivers this month?"
/nexus "Create a DQX rule for fact_ap_invoice"
/nexus-qlik "Step 0: Scan /7 - Qlik Migration/Procurement Analytics/"
/nexus-agent 32 "What Oracle EBS tables relate to AP aging?"
/nexus-status
```

---

## Architecture

```
VS Code (Claude Code) → /nexus slash command
  → Databricks CLI (jobs submit, --profile DEV)
    → Phoenix Shared Compute (0925-054849-fb85h9tq)
      → 00_meta_supervisor notebook
        → FMAPI: databricks-claude-sonnet-4-6
          → Intent classification (W1/W2/W3/W4)
            → Agent routing → Response back to VS Code
```

All LLM inference happens on Databricks. Zero Anthropic direct calls.

---

## Regenerating the Command Files

The source generator script that creates the workspace files is at:
`/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Project Docs/vscode_claude_code/`

To regenerate after edits, run the Python generator notebook or manually edit the `.md` files in that workspace folder.

---

## Known Issues (from first test)

1. **`SQL_WAREHOUSE_ID` placeholder in `nexus-status.md`** — Replace with actual warehouse ID: `9f6fb545dba4f67b`
2. **Single-quote escaping** in `nexus-status.md` bash `--json` argument — The SQL string literals (`'ACTIVE'`, `'CLOSED'`) break out of the outer single-quoted argument. Fix: use double quotes for the outer `--json` or escape inner quotes.
3. **Registry was stale** — Fixed Aug 4, 2026 (64 agents inserted). Now shows 152 registered, 108 ACTIVE.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Commands don't appear | Restart Claude Code: `Cmd+Shift+P` → "Developer: Reload Window" |
| `databricks: command not found` | Install Databricks CLI: `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh \| sh` |
| Auth error | Re-authenticate: `databricks auth login --profile DEV` |
| Cluster not running | Start Phoenix: `databricks clusters start 0925-054849-fb85h9tq --profile DEV` |
| Job timeout | Increase poll loop or check cluster cold-start time |

---

## Future: Upgrade to Option D (Custom MCP Server)

See `VSCODE_NEXUS_INTEGRATION_OPTIONS.md` in this same folder for the full MCP server approach with streaming support and direct FMAPI calls (no cluster cold-start).
