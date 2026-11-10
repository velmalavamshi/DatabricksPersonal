# Databricks notebook source
# DBTITLE 1,Welcome
# MAGIC %md
# MAGIC # 🤖 Hologic AI Agent Platform — Interactive Mode
# MAGIC
# MAGIC ## How to Use (3 Simple Steps)
# MAGIC
# MAGIC 1. **Type your request** in the text box below (it will appear at the top of the notebook)
# MAGIC 2. **Click "Run All"** (the ▶▶ button in the toolbar) or press `Ctrl+Shift+Enter`
# MAGIC 3. **Read the results** — the AI agents will process your request and show the output below
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## What You Can Ask
# MAGIC
# MAGIC | Type of Request | Example |
# MAGIC | --- | --- |
# MAGIC | Build something new | "Create a Silver-layer supplier dimension from Oracle EBS" |
# MAGIC | Fix a problem | "Why is job 613621324309790 failing every hour?" |
# MAGIC | Reduce costs | "Find our most expensive queries and recommend optimizations" |
# MAGIC | Review code | "Review the latest Data Engineer output for security issues" |
# MAGIC | Design architecture | "Design the Medallion architecture for Salesforce Account data" |
# MAGIC | Generate code | "Write a MERGE statement for incremental loading of AP invoices" |
# MAGIC | Check health | "Show me which agents are healthy and which have issues" |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **No coding required.** Just type what you need in plain English.

# COMMAND ----------

# DBTITLE 1,Step 1: Your Request Goes Here
# ══════════════════════════════════════════════════════════════════════
# 👇 TYPE YOUR REQUEST HERE (between the quotes)
# ══════════════════════════════════════════════════════════════════════

dbutils.widgets.text("request", "", "💬 How many agents are ready?")

# You can also type directly here instead of the widget:
# MY_REQUEST = "Create a Gold-layer customer dimension from Salesforce"

print("✅ Ready! Type your request in the box above, then Run All.")
print("   Or edit MY_REQUEST in this cell and run.")

# COMMAND ----------

# DBTITLE 1,Step 2: Load the Agent Platform
# MAGIC %run ./00_supervisor_agent

# COMMAND ----------

# DBTITLE 1,Step 3: Process Your Request
# ══════════════════════════════════════════════════════════════════════
# This cell does all the work! Just Run All and wait.
# ══════════════════════════════════════════════════════════════════════

# Get the request from the widget or fallback
try:
    user_request = dbutils.widgets.get("request")
except:
    user_request = ""

# Allow override via variable (if someone edits the cell directly)
try:
    if MY_REQUEST:
        user_request = MY_REQUEST
except NameError:
    pass

# Check if we have a request
if not user_request or user_request.strip() == "":
    print("⚠️ No request entered!")
    print("")
    print("Please do ONE of these:")
    print("  1. Type your request in the text box at the top of the notebook")
    print("  2. Or edit Cell 2 and set: MY_REQUEST = \"your request here\"")
    print("")
    print("Then click Run All again.")
else:
    # Process the request through the Supervisor
    print("\n" + "═" * 70)
    print("  🤖 PROCESSING YOUR REQUEST")
    print("═" * 70)
    print(f"  You asked: {user_request}")
    print("═" * 70)
    print("")
    print("⏳ Working... (this typically takes 30-90 seconds)")
    print("   The Supervisor is figuring out which agents to use...")
    print("")
    
    # RUN THE SUPERVISOR
    final_result = process_request(user_request)
    
    # Display the result nicely
    print("\n")
    print("═" * 70)
    print("  ✅ DONE! Here's your result:")
    print("═" * 70)
    print("\n")

# COMMAND ----------

# DBTITLE 1,Your Results
# Display the final result in a readable format
try:
    if final_result and user_request.strip():
        # Show as markdown for nice formatting
        displayHTML(f"<div style='font-family: -apple-system, sans-serif; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #1B2A4A;'><pre style='white-space: pre-wrap; font-size: 14px;'>{final_result}</pre></div>")
except NameError:
    print("No results yet. Enter a request above and Run All.")

# COMMAND ----------

# DBTITLE 1,What Just Happened?
# MAGIC %md
# MAGIC ## What Just Happened Behind the Scenes
# MAGIC
# MAGIC When you hit "Run All", the Supervisor Agent did this:
# MAGIC
# MAGIC ```
# MAGIC ┌──────────────────────────────────────────────────────────┐
# MAGIC │ 1. Read your request                                    │
# MAGIC │ 2. Classified what type of work it is                   │
# MAGIC │ 3. Chose the right agents for the job                   │
# MAGIC │ 4. Ran those agents (passing info between them)          │
# MAGIC │ 5. Checked the outputs for quality and safety            │
# MAGIC │ 6. Merged everything into one final answer               │
# MAGIC └──────────────────────────────────────────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC All results are automatically saved. You can find past results with:
# MAGIC ```sql
# MAGIC SELECT * FROM mde_dev.test_schema.agent_outputs 
# MAGIC WHERE agent_name = 'supervisor' 
# MAGIC ORDER BY timestamp DESC;
# MAGIC ```
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Want to Run Again?
# MAGIC
# MAGIC Just change your text in the box at the top and click **Run All** again. Each run is independent.
# MAGIC
# MAGIC ## Need Help?
# MAGIC
# MAGIC Try these starter requests:
# MAGIC - "Show me the health of all agents"
# MAGIC - "What are the top 5 failing jobs this week?"
# MAGIC - "Design a fact table for purchase orders from Oracle EBS"
# MAGIC - "Review security for our Gold layer tables"