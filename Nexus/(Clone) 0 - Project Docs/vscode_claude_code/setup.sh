#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════
# NEXUS → Claude Code Deployment Script
# Run this from your VS Code project root (or any directory with .claude/)
#
# Prerequisites:
#   1. Claude Code extension installed in VS Code
#   2. Databricks CLI installed + DEV profile configured
#   3. Phoenix cluster ID (replace 0925-054849-fb85h9tq below)
# ══════════════════════════════════════════════════════════════════════════

set -e

# ── Configuration ─────────────────────────────────────────────────────────
# TODO: Replace with your actual Phoenix cluster ID
0925-054849-fb85h9tq="<PASTE-YOUR-CLUSTER-ID-HERE>"
# Get it via: databricks clusters list --profile DEV | grep Phoenix

# ── Create directory structure ────────────────────────────────────────────
mkdir -p .claude/commands

echo "🚀 Deploying NEXUS slash commands for Claude Code..."

# ── Download from Databricks workspace ────────────────────────────────────
WS_PATH="/Workspace/Users/sameet.patel@hologic.com/5 - Personal Projects/5 - AI Multi Agents/0 - Project Docs/vscode_claude_code"

databricks workspace export "$WS_PATH/CLAUDE.md" .claude/../CLAUDE.md --profile DEV 2>/dev/null ||   echo "⚠️  Manual copy needed: CLAUDE.md"

databricks workspace export "$WS_PATH/commands/nexus.md" .claude/commands/nexus.md --profile DEV 2>/dev/null ||   echo "⚠️  Manual copy needed: commands/nexus.md"

databricks workspace export "$WS_PATH/commands/nexus-qlik.md" .claude/commands/nexus-qlik.md --profile DEV 2>/dev/null ||   echo "⚠️  Manual copy needed: commands/nexus-qlik.md"

databricks workspace export "$WS_PATH/commands/nexus-agent.md" .claude/commands/nexus-agent.md --profile DEV 2>/dev/null ||   echo "⚠️  Manual copy needed: commands/nexus-agent.md"

databricks workspace export "$WS_PATH/commands/nexus-status.md" .claude/commands/nexus-status.md --profile DEV 2>/dev/null ||   echo "⚠️  Manual copy needed: commands/nexus-status.md"

# ── Replace placeholder cluster ID ───────────────────────────────────────
if [ "$0925-054849-fb85h9tq" != "<PASTE-YOUR-CLUSTER-ID-HERE>" ]; then
  sed -i "" "s/0925-054849-fb85h9tq/$0925-054849-fb85h9tq/g" .claude/commands/nexus.md 2>/dev/null ||   sed -i "s/0925-054849-fb85h9tq/$0925-054849-fb85h9tq/g" .claude/commands/nexus.md
  
  sed -i "" "s/0925-054849-fb85h9tq/$0925-054849-fb85h9tq/g" .claude/commands/nexus-qlik.md 2>/dev/null ||   sed -i "s/0925-054849-fb85h9tq/$0925-054849-fb85h9tq/g" .claude/commands/nexus-qlik.md
  
  echo "✅ Cluster ID injected: $0925-054849-fb85h9tq"
else
  echo "⚠️  Replace 0925-054849-fb85h9tq in .claude/commands/*.md"
  echo "   Get it: databricks clusters list --profile DEV | grep Phoenix"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ NEXUS Claude Code integration deployed!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Available commands in Claude Code:"
echo "  /nexus <request>         — Route through Meta Supervisor (134 agents)"
echo "  /nexus-qlik <step>       — Qlik Migration (Agent 88 → 89-96)"
echo "  /nexus-agent <id> <req>  — Call specific agent directly"
echo "  /nexus-status            — Platform health check"
echo ""
echo "All LLM inference → Databricks FMAPI (databricks-claude-sonnet-4-6)"
echo "Zero Anthropic direct calls."
echo "═══════════════════════════════════════════════════════════════"
