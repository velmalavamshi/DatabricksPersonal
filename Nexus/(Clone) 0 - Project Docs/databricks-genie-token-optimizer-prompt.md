# Databricks Genie Prompt — Token Optimizer Setup Notebook

Paste this prompt into Databricks Genie (or any AI assistant connected to your Databricks workspace).
Genie will generate and execute a notebook that installs and configures all four token optimization layers.

---

## PROMPT (copy everything below the line)

---

You are a Databricks automation agent with access to this workspace. Your task is to create and run a Databricks notebook that installs and configures a 4-layer token optimization stack for a multi-agent system. The goal is to reduce token consumption across all agents by 85–95%.

**Create a new notebook called** `token_optimizer_setup` in the current user's home folder (`/Users/{current_user}/token_optimizer_setup`). The notebook must use Python as the default language.

The notebook must contain exactly the following cells, in order:

---

### Cell 1 — Title and Overview (Markdown)

```
# Token Optimizer — 4-Layer Stack Setup
## For Databricks Multi-Agent Systems

This notebook installs and configures four token optimization tools that compound to reduce
agent token consumption by 85–95%:

| Layer | Tool | Claim | What it eliminates |
|---|---|---|---|
| 0 | code-review-graph | 8.2× avg · 49× monorepo | Re-reading entire repo on every change |
| 1 | codegraph | 47% fewer tokens | File scanning via grep/glob |
| 2 | Graphify | 71.5× per query | Cold-start file reads |
| 3 | claude-mem | 10× per session | Cross-session context loss |

**GitHub sources:**
- https://github.com/tirth8205/code-review-graph (most credible — reproducible benchmarks, native .ipynb support)
- https://github.com/colbymchenry/codegraph
- https://github.com/safishamsi/graphify
- https://github.com/thedotmack/claude-mem

Run all cells top to bottom. Each section is idempotent — safe to re-run.
```

---

### Cell 2 — Environment Detection (Python)

```python
import subprocess
import sys
import os
import json
from pathlib import Path

# Detect runtime
IS_DATABRICKS = "DATABRICKS_RUNTIME_VERSION" in os.environ
RUNTIME_VERSION = os.environ.get("DATABRICKS_RUNTIME_VERSION", "local")
WORKSPACE_URL = os.environ.get("DATABRICKS_HOST", "unknown")
PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"
NODE_AVAILABLE = subprocess.run(["which", "node"], capture_output=True).returncode == 0
NPX_AVAILABLE = subprocess.run(["which", "npx"], capture_output=True).returncode == 0

print(f"Runtime:        {'Databricks ' + RUNTIME_VERSION if IS_DATABRICKS else 'Local'}")
print(f"Python:         {PYTHON_VERSION}")
print(f"Node/NPX:       {'✓ available' if NODE_AVAILABLE else '✗ not found — claude-mem and codegraph need Node 18+'}")
print(f"Workspace:      {WORKSPACE_URL}")
print()

# Warn if Python < 3.10
if sys.version_info < (3, 10):
    print("⚠ WARNING: code-review-graph and graphify require Python 3.10+.")
    print(f"  Current: {PYTHON_VERSION}. Switch to a DBR 13.3+ cluster.")
else:
    print(f"✓ Python {PYTHON_VERSION} — meets requirements for all tools")
```

---

### Cell 3 — Layer 0: Install code-review-graph (Python)

```python
# ============================================================
# LAYER 0: code-review-graph (tirth8205)
# Blast-radius analysis — agents read only affected files
# 8.2× average token reduction · 49× on monorepos
# Native Jupyter/.ipynb support with multi-language cell parsing
# ============================================================

print("Installing code-review-graph...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "code-review-graph", "--quiet", "--upgrade"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("✓ code-review-graph installed")
else:
    print(f"✗ Install failed: {result.stderr[-500:]}")

# Verify
verify = subprocess.run(
    [sys.executable, "-m", "code_review_graph", "--version"],
    capture_output=True, text=True
)
if verify.returncode == 0:
    print(f"  Version: {verify.stdout.strip()}")
else:
    # Try alternate entry point
    verify2 = subprocess.run(["code-review-graph", "--version"], capture_output=True, text=True)
    print(f"  Version: {verify2.stdout.strip() if verify2.returncode == 0 else 'installed (version check unavailable in this runtime)'}")
```

---

### Cell 4 — Build code-review-graph Index (Python)

```python
# Build the knowledge graph for the current workspace checkout
# Adjust REPO_PATH to your actual Databricks repo mount point

REPO_PATH = os.environ.get("REPO_ROOT", "/Workspace/Repos")  # adjust as needed
CRG_CONFIG_PATH = Path(REPO_PATH) / ".code-review-graph"

print(f"Target path: {REPO_PATH}")
print()

if not Path(REPO_PATH).exists():
    print(f"⚠ Path {REPO_PATH} not found.")
    print("  Set REPO_ROOT environment variable to your actual repo path, e.g.:")
    print("  /Workspace/Repos/your-username/your-repo")
    print()
    print("  Then re-run this cell. Skipping build for now.")
else:
    print("Building code-review-graph index (first run ~10–60s depending on repo size)...")
    build = subprocess.run(
        ["code-review-graph", "build", "--repo", REPO_PATH],
        capture_output=True, text=True, cwd=REPO_PATH
    )
    if build.returncode == 0:
        print("✓ Graph built successfully")
        print(build.stdout[-800:] if build.stdout else "")
    else:
        print(f"Build output: {build.stdout[-400:]}")
        print(f"Errors: {build.stderr[-400:]}")

    # Show graph stats
    stats = subprocess.run(
        ["code-review-graph", "status", "--repo", REPO_PATH],
        capture_output=True, text=True, cwd=REPO_PATH
    )
    if stats.returncode == 0:
        print()
        print("Graph stats:")
        print(stats.stdout)
```

---

### Cell 5 — Layer 2: Install Graphify (Python)

```python
# ============================================================
# LAYER 2: Graphify (safishamsi)
# Full knowledge graph — notebooks, schemas, docs, images
# 71.5× fewer tokens per query vs reading raw files
# NOTE: Stars grew very fast (~59k) — verify before production use
# ============================================================

print("Installing graphify...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "graphifyy", "--quiet", "--upgrade"],
    # Note: PyPI package is 'graphifyy' while the CLI command is 'graphify'
    capture_output=True, text=True
)
if result.returncode == 0:
    print("✓ graphify installed")
else:
    print(f"✗ Install failed: {result.stderr[-500:]}")

# Verify
verify = subprocess.run(["graphify", "--version"], capture_output=True, text=True)
print(f"  Version: {verify.stdout.strip() if verify.returncode == 0 else 'installed (CLI path may need refresh)'}")
print()
print("Next step (run in Claude Code after this notebook completes):")
print("  /graphify .         ← builds knowledge graph for your Databricks repo")
print("  graphify hook install  ← auto-rebuilds graph on every git commit")
print()
print("For Databricks notebooks specifically, graphify handles .ipynb files")
print("and can ingest Unity Catalog schema exports, pipeline YAML, and docs.")
```

---

### Cell 6 — Layer 1 & 3: Node-based tools check (Python)

```python
# ============================================================
# LAYER 1: codegraph (colbymchenry)  — requires Node 22.5+
# LAYER 3: claude-mem (thedotmack)   — requires Node 18+
# These are npm tools. Databricks clusters may not have Node.
# This cell provides the install commands for your local machine
# or a Databricks cluster with Node configured.
# ============================================================

print("=" * 60)
print("LAYER 1: codegraph + LAYER 3: claude-mem")
print("=" * 60)
print()

if NODE_AVAILABLE:
    node_ver = subprocess.run(["node", "--version"], capture_output=True, text=True)
    print(f"✓ Node found: {node_ver.stdout.strip()}")
    
    # Check Node version for codegraph (needs 22.5+)
    ver_parts = node_ver.stdout.strip().lstrip("v").split(".")
    node_major = int(ver_parts[0]) if ver_parts else 0
    
    if node_major >= 22:
        print("✓ Node 22+ confirmed — codegraph can install")
        # Install codegraph
        print()
        print("Installing codegraph...")
        cg = subprocess.run(
            ["npx", "--yes", "@colbymchenry/codegraph"],
            capture_output=True, text=True, timeout=120
        )
        print("✓ codegraph install triggered" if cg.returncode == 0 else f"codegraph: {cg.stderr[-300:]}")
    elif node_major >= 18:
        print(f"⚠ Node {node_major} — claude-mem will work, but codegraph needs Node 22.5+")
    
    if NPX_AVAILABLE:
        print()
        print("Installing claude-mem...")
        cm = subprocess.run(
            ["npx", "claude-mem", "install"],
            capture_output=True, text=True, timeout=120
        )
        print("✓ claude-mem installed" if cm.returncode == 0 else f"claude-mem: {cm.stderr[-300:]}")
else:
    print("⚠ Node.js not found on this cluster.")
    print()
    print("To install codegraph and claude-mem, run these commands")
    print("on your LOCAL MACHINE (where Claude Code runs):")
    print()
    print("  # codegraph (Layer 1 — symbol index)")
    print("  npx @colbymchenry/codegraph")
    print("  codegraph init -i")
    print()
    print("  # claude-mem (Layer 3 — persistent memory)")
    print("  npx claude-mem install")
    print()
    print("Both tools wire into Claude Code automatically on install.")
    print("They run as MCP servers on your local machine, not on the cluster.")
```

---

### Cell 7 — MCP Configuration for Databricks Agents (Python)

```python
# ============================================================
# Generate MCP server configuration for your Databricks agents
# This config tells each agent which MCP tools are available
# ============================================================

MCP_CONFIG = {
    "mcpServers": {
        "code-review-graph": {
            "command": "code-review-graph",
            "args": ["serve"],
            "description": "Blast-radius analysis — 8.2× avg token reduction on code review",
            "tools": [
                "get_minimal_context_tool",
                "get_impact_radius_tool", 
                "get_review_context_tool",
                "detect_changes_tool",
                "query_graph_tool",
                "semantic_search_nodes_tool"
            ],
            "note": "Use --tools flag to limit exposed tools in token-constrained environments"
        },
        "codegraph": {
            "command": "codegraph",
            "args": ["serve"],
            "description": "Symbol graph — 47% fewer tokens on file/symbol lookups",
            "note": "Run: npx @colbymchenry/codegraph on local machine first"
        },
        "claude-mem": {
            "command": "claude-mem",
            "args": ["serve"],
            "description": "Persistent memory — 10× per session via compressed context injection",
            "note": "Run: npx claude-mem install on local machine first"
        }
    },
    "agentInstructions": {
        "onSessionStart": [
            "1. Call get_minimal_context_tool first (~100 tokens) to orient yourself",
            "2. Call codegraph status to confirm symbol index is fresh",
            "3. claude-mem will auto-inject relevant memory from past sessions"
        ],
        "onFileChange": [
            "1. Call detect_changes_tool with the changed file paths",
            "2. Call get_impact_radius_tool to get blast radius",
            "3. Read ONLY the files in the blast radius result — not the whole repo"
        ],
        "onCodeReview": [
            "1. Call get_review_context_tool for token-optimised structural context",
            "2. Use query_graph_tool for callers/callees if you need deeper analysis",
            "3. Use get_knowledge_gaps_tool to find untested hotspots"
        ]
    }
}

# Write config to workspace
config_path = Path("/tmp/mcp_token_optimizer_config.json")
config_path.write_text(json.dumps(MCP_CONFIG, indent=2))
print(f"✓ MCP configuration written to {config_path}")
print()
print("Copy this config into your agent system prompt or MCP client config:")
print()
print(json.dumps(MCP_CONFIG, indent=2))
```

---

### Cell 8 — Agent System Prompt Templates (Python)

```python
# ============================================================
# System prompt snippets to inject into each Databricks agent
# These instructions tell agents HOW to use the four tools
# ============================================================

SUPERVISOR_PROMPT_INJECTION = """
## Token Optimization Instructions

You operate within a 4-layer token optimization stack. Follow these rules strictly:

### Before reading ANY file:
1. Call `get_minimal_context_tool` first — always. This costs ~100 tokens and may answer your question entirely.
2. If you need symbol information, call `codegraph_explore` — never use grep or glob.
3. If reviewing a change, call `detect_changes_tool` + `get_impact_radius_tool` first.
   Read ONLY the files in the blast radius. Never read the whole repo.

### Session start:
- claude-mem has already injected relevant context from past sessions into your context window.
- Do NOT re-ask for project context that may already be present. Check first.

### When routing tasks to sub-agents:
- Pass the blast radius file list to the relevant agent so it doesn't re-compute it.
- Pass any relevant memory observations from claude-mem search results.

### Token budget awareness:
- Target: resolve each task in under 5,000 tokens of tool calls.
- If you find yourself reading more than 10 files, stop and re-query the graph first.
"""

NOTEBOOK_REVIEWER_PROMPT_INJECTION = """
## Notebook Review Instructions (Token-Optimized)

You review Databricks notebooks (.ipynb files). Use this workflow:

1. `detect_changes_tool` → identify which notebooks changed
2. `get_impact_radius_tool` → find all affected notebooks, pipelines, schemas
3. `get_review_context_tool` → get structural summary for affected files only
4. For each changed notebook cell: check `query_graph_tool` for callers/callees
5. `get_knowledge_gaps_tool` → identify untested hotspots introduced by this change
6. `get_suggested_questions_tool` → auto-generate review questions from graph analysis

code-review-graph natively parses .ipynb with multi-language cell support (Python, R, SQL).
Never read the raw .ipynb JSON — always query via graph tools.
"""

PIPELINE_MONITOR_PROMPT_INJECTION = """
## Pipeline Monitor Instructions (Token-Optimized)

1. On pipeline failure: call `detect_changes_tool` with recently changed files first
2. Use `get_impact_radius_tool` to identify which downstream pipelines are affected
3. Check claude-mem for past similar failures: search("pipeline failure {pipeline_name}")
4. Use `query_graph_tool` to trace the failing function's callers and callees
5. Save your diagnosis to memory so future sessions don't re-investigate from scratch
"""

prompts = {
    "Supervisor Agent": SUPERVISOR_PROMPT_INJECTION,
    "Notebook Reviewer": NOTEBOOK_REVIEWER_PROMPT_INJECTION,
    "Pipeline Monitor": PIPELINE_MONITOR_PROMPT_INJECTION,
}

print("=" * 60)
print("AGENT SYSTEM PROMPT INJECTIONS")
print("Add these to your agent system prompts in agent_registry.json")
print("=" * 60)

for agent_name, prompt in prompts.items():
    print(f"\n{'='*40}")
    print(f"AGENT: {agent_name}")
    print(f"{'='*40}")
    print(prompt)

# Save to file for easy reference
output_path = Path("/tmp/agent_prompt_injections.md")
with output_path.open("w") as f:
    for agent_name, prompt in prompts.items():
        f.write(f"## {agent_name}\n\n```\n{prompt}\n```\n\n---\n\n")
print(f"\n✓ Prompt injections saved to {output_path}")
```

---

### Cell 9 — Verification Summary (Python)

```python
# ============================================================
# Final verification — check what's installed and working
# ============================================================

import importlib

print("=" * 60)
print("TOKEN OPTIMIZER — INSTALLATION SUMMARY")
print("=" * 60)
print()

checks = []

# code-review-graph
try:
    result = subprocess.run(["code-review-graph", "status"], capture_output=True, text=True, timeout=10)
    checks.append(("code-review-graph", "✓ installed", "#E8C547"))
except FileNotFoundError:
    checks.append(("code-review-graph", "✗ not found — check PATH", "red"))

# graphify
try:
    result = subprocess.run(["graphify", "--version"], capture_output=True, text=True, timeout=10)
    checks.append(("graphify", "✓ installed", "#00C896"))
except FileNotFoundError:
    checks.append(("graphify", "✗ not found — check PATH", "red"))

# codegraph (local machine only)
if NODE_AVAILABLE:
    try:
        result = subprocess.run(["codegraph", "status"], capture_output=True, text=True, timeout=10)
        checks.append(("codegraph", "✓ installed", "#4C9BFF"))
    except FileNotFoundError:
        checks.append(("codegraph", "⚠ run: npx @colbymchenry/codegraph (local machine)", "#FF9900"))
else:
    checks.append(("codegraph", "⚠ install on local machine: npx @colbymchenry/codegraph", "#FF9900"))

# claude-mem (local machine only)
if NODE_AVAILABLE:
    try:
        result = subprocess.run(["claude-mem", "status"], capture_output=True, text=True, timeout=10)
        checks.append(("claude-mem", "✓ installed", "#FF6B35"))
    except FileNotFoundError:
        checks.append(("claude-mem", "⚠ run: npx claude-mem install (local machine)", "#FF9900"))
else:
    checks.append(("claude-mem", "⚠ install on local machine: npx claude-mem install", "#FF9900"))

for tool, status, _ in checks:
    print(f"  {tool:<30} {status}")

print()
print("NEXT STEPS:")
print()
print("  1. On your LOCAL machine (where Claude Code runs):")
print("     npx @colbymchenry/codegraph      ← symbol index (Layer 1)")
print("     npx claude-mem install            ← persistent memory (Layer 3)")
print()
print("  2. In Claude Code (in your Databricks repo):")
print("     /graphify .                       ← build knowledge graph (Layer 2)")
print("     graphify hook install             ← auto-rebuild on git commit")
print("     code-review-graph watch           ← auto-update blast-radius index")
print()
print("  3. Add the prompt injections from Cell 8 to your agent system prompts")
print("     in agent_registry.json")
print()
print("  4. Restart your Claude Code session — all 4 layers will activate.")
print()
print("Expected result: 85–95% reduction in token consumption across your")
print("Databricks multi-agent system.")
```

---

## Notes for Genie

- If Genie asks which cluster to use, select **DBR 14.0+ or higher** (Python 3.10+ required).
- If Genie asks about permissions, the notebook only needs **cluster-level pip install** access and write access to `/tmp`.
- `codegraph` and `claude-mem` are Node.js tools — Genie should note in the notebook that they install on the **local developer machine** (where Claude Code runs), not on the Databricks cluster.
- After Genie creates the notebook, ask it: **"Run all cells and show me the summary output from Cell 9."**
