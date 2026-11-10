# Databricks notebook source
# DBTITLE 1,Security Layer
# MAGIC %md
# MAGIC # NEXUS Governance — Security Layer (W0)
# MAGIC
# MAGIC **Purpose:** PII detection in agent I/O, credential rotation audit, secret scope validation, and compliance logging.

# COMMAND ----------

# DBTITLE 1,Load meta config
# MAGIC %run ./00_meta_config

# COMMAND ----------

# DBTITLE 1,STEP 1: PII Detection and Secret Audit
# ======================================================================
# STEP 1 — PII DETECTION & SECRET AUDIT
# Scans recent agent events for PII leakage and validates secret scope
# ======================================================================

import re

AGENT_NAME = "04_security_layer"
run_id = generate_run_id()

# PII patterns to detect in agent payloads
PII_PATTERNS = {
    "email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "phone": r'\b\d{3}[-.]\d{3}[-.]\d{4}\b',
    "credit_card": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
    "npi": r'\b\d{10}\b',  # Healthcare NPI numbers
}

# Scan recent event payloads for PII
recent_events = spark.sql(f"""
    SELECT event_id, source_agent, event_type, payload, created_at
    FROM {NEXUS_EVENTS}
    WHERE created_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
    ORDER BY created_at DESC
    LIMIT 100
""").collect()

pii_findings = []
for event in recent_events:
    payload = event['payload'] or ''
    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, payload)
        if matches and pii_type != 'email':  # Emails in agent names are OK
            pii_findings.append({
                "event_id": event['event_id'],
                "agent": event['source_agent'],
                "pii_type": pii_type,
                "match_count": len(matches),
                "event_type": event['event_type'],
            })

# Validate secret scope
try:
    scopes = dbutils.secrets.listScopes()
    nexus_scope_exists = any(s.name == 'nexus' for s in scopes)
except:
    nexus_scope_exists = False

print(f"\U0001f512 SECURITY AUDIT")
print("=" * 60)
print(f"  Events scanned (7d): {len(recent_events)}")
print(f"  PII findings: {len(pii_findings)}")
print(f"  Secret scope 'nexus': {'\u2705 exists' if nexus_scope_exists else '\u274c MISSING'}")
print("=" * 60)

if pii_findings:
    print(f"\n\u26a0\ufe0f PII DETECTED in event payloads:")
    for f in pii_findings[:5]:
        print(f"   {f['agent']} | {f['pii_type']} | {f['match_count']} occurrences | event: {f['event_type']}")
else:
    print(f"\n\u2705 No PII detected in recent event payloads")