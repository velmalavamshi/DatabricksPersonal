# Qlik Migration — 4.4.1 Procurement Analytics

## Overview

| Attribute | Value |
|---|---|
| **Qlik App Name** | 4.3 Procure materials and services_LAYOUT |
| **QVF File** | Procurement Analytics.qvf |
| **Author** | Jim Beierschmitt |
| **Created** | August 4, 2015 |
| **Last Reload** | May 24, 2026 1:04:41 PM |
| **QVB Version** | 12.80.20200+2024-02-09 |
| **Reload User** | HOLOGIC\qvpublisherdev |
| **Server** | Windows Server 2012 R2 (64-bit), 32 cores |
| **Qlik Sense Theme** | card (Hologic branding: #4477aa title, white text) |

---

## Source Files Inventory

| File | Purpose |
|---|---|
| `LoadScript.txt` | Full QlikView load script (~2,404 lines, 12 tabs) |
| `4.4.1 Purchasing Analytics_LAYOUT.qvw.log` | Reload execution log (May 24, 2026) |
| `Procurement Analytics.qvf` | Qlik Sense app (binary) |
| `QlikViewProject.xml` | QlikView project metadata |
| `DocProperties.xml` | Document-level properties (color maps, locale, captions) |
| `SH01.xml` | Sheet 1 — "Main" tab layout |
| `TB01.xml` | Table box definition |
| `TX01.xml` – `TX04.xml` | Text objects |
| `TopLayout.xml` | Top-level layout definition |
| `DocInternals.xml` | Internal document state |
| `AllProperties.xml` | Consolidated object properties |
| `Module.txt` | VBScript macros (if any) |
| `DocBinary.dat` | Binary data store |
| `Procurement-Analytics-extract/app.json` | Qlik Sense extracted app properties |

---

## Data Model Architecture

### Load Script Tabs (in order)

| Tab | Purpose | Key Tables Loaded |
|---|---|---|
| **Main** | Environment setup, variable initialization | Environment variables, QVC runtime |
| **Mapping** | Lookup maps for org codes, process flags, planners, MRP codes, releases, users | 6 mapping tables |
| **sup** | Suppliers (AP_SUPPLIERS) | `sup` — VENDOR_ID → SUPPLIER, SUPPLIER_NUMBER |
| **ssite** | Supplier Sites (AP_SUPPLIER_SITES_ALL) — LEFT JOIN to sup | Site, City, State, ZIP, Country, Address |
| **poh** | PO Headers (PO_HEADERS_ALL) | PO_NUMBER, AUTHORIZATION_STATUS, CURRENCY, TYPE_LOOKUP_CODE, RATE |
| **plla** | PO Line Locations (PO_LINE_LOCATIONS_ALL) — LEFT JOIN to poh_temp | Shipment, NEED_BY_DATE, PROMISED_DATE, Org Code |
| **pol** | PO Lines (PO_LINES_ALL) — LEFT JOIN to poh_temp | LINE_NUM, UNIT_PRICE, ITEM_ID, CANCEL_FLAG |
| **pda** | PO Distributions (PO_DISTRIBUTIONS_ALL) — LEFT JOIN to poh_temp | QTY_ORDERED, QTY_DELIVERED, QTY_BILLED, QTY_CANCELLED |
| **RCV** | Receiving Transactions (RCV_TRANSACTIONS) — LEFT JOIN; RCV_SHIPMENT_HEADERS | RETURN TO VENDOR transactions, Receipt Num |
| **pav** | Buyer/Agent names (PO_AGENTS_V) | AGENT_ID → BUYER |
| **msi** | Item Master (MTL_SYSTEM_ITEMS_B) | ITEM, ITEM_DESCRIPTION, lead times, planner, lot/serial control |
| **icd** | Item Cost (CST_ITEM_COST_TYPE_V + GL_ITEM_CST) | STANDARD_COST (frozen=1, process=1000) |
| **icd continued** | Process manufacturing item costs (GL_ITEM_CST) | Concatenated to icd |
| **hao** | Organization Names (HR_ALL_ORGANIZATION_UNITS) | ORGANIZATION_NAME |
| **prd** | Requisition Distributions (PO_REQ_DISTRIBUTIONS_ALL) — LEFT JOIN to poh | Links PO dist → req line |
| **prla** | Requisition Lines (PO_REQUISITION_LINES_ALL) — LEFT JOIN to poh | Part_Number (manufacturer) |
| **prha** | Requisition Headers (PO_REQUISITION_HEADERS_ALL) — LEFT JOIN to poh | REQUISITION_NUM |
| **Change Log** | Script end, exit | Duration calc |

---

## Data Model (Star Schema)

```
                         ┌─────────┐
                         │   sup   │ (Suppliers)
                         │ %VENDOR │
                         │  _ID    │
                         └────┬────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
               ┌────┴────┐        ┌────┴────┐
               │  ssite  │        │   poh   │ (PO Headers — FACT)
               │%VENDOR_ │        │%PO_HEADER│
               │ SITE_ID │        │   _ID    │
               └─────────┘        └────┬────┘
                                       │
              ┌──────────┬─────────────┼──────────────┬──────────┐
              │          │             │              │          │
         ┌────┴────┐┌────┴────┐  ┌────┴────┐  ┌─────┴────┐┌────┴────┐
         │  plla   ││  pol    │  │   pda   │  │   pav    ││  RCV    │
         │%LINE_   ││%PO_LINE_│  │%LINE_   │  │%AGENT_ID ││%PO_HDR  │
         │LOCATION ││  ID     │  │LOCATION │  └──────────┘│%PO_LINE │
         │  _ID    │└─────────┘  │  _ID    │              └─────────┘
         └─────────┘             └────┬────┘
                                      │
                                 ┌────┴────┐
                                 │   prd   │ → prla → prha
                                 │%DISTRI- │   (Requisition chain)
                                 │BUTION_ID│
                                 └─────────┘

         ┌─────────┐       ┌─────────┐       ┌─────────┐
         │   msi   │       │   icd   │       │   hao   │
         │%INVENT- │       │%INVENT- │       │%DEST_   │
         │ORY_ITEM │       │ORY_ITEM │       │ORG_ID   │
         │  _ID    │       │  _ID    │       └─────────┘
         └─────────┘       └─────────┘
```

### Key Composite Keys
- `%INVENTORY_ITEM_ID` = `ORGANIZATION_ID || '|' || INVENTORY_ITEM_ID`
- `%VENDOR_SITE_ID` links supplier sites to PO headers
- `%AGENT_ID` links PO headers to buyers

---

## Calculated Fields (in poh final load)

| Field | Expression |
|---|---|
| `TOTAL_SHIPMENT_AMT` | `pda.QUANTITY_ORDERED * pol.UNIT_PRICE * poh.RATE` |
| `DOLLAR_AMT_RCVD` | `pda.QUANTITY_DELIVERED * pol.UNIT_PRICE * poh.RATE` |
| `DOLLAR_AMT_OPEN` | `TOTAL_SHIPMENT_AMT - DOLLAR_AMT_RCVD` |

---

## QVD Source Files (Oracle EBS)

| QVD Path | Oracle Table |
|---|---|
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.ap_suppliers.qvd` | AP_SUPPLIERS |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.ap_supplier_sites_all.qvd` | AP_SUPPLIER_SITES_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.po_headers_all.qvd` | PO_HEADERS_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.PO_LINE_LOCATIONS_ALL.qvd` | PO_LINE_LOCATIONS_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.po_lines_all.qvd` | PO_LINES_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.PO_DISTRIBUTIONS_ALL.qvd` | PO_DISTRIBUTIONS_ALL |
| `3_Data_Repository/Oracle_EBS/PO.RCV_Transactions.qvd` | RCV_TRANSACTIONS |
| `3_Data_Repository/Oracle_EBS/PO.RCV_SHIPMENT_HEADERS.qvd` | RCV_SHIPMENT_HEADERS |
| `3_Data_Repository/Oracle_EBS/PO_RELEASES_ALL.qvd` | PO_RELEASES_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.po_agents_v.qvd` | PO_AGENTS_V |
| `3_Data_Oracle_EBS/Master Data/Item Master/inv.mtl_system_items_b.qvd` | MTL_SYSTEM_ITEMS_B |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.CST_ITEM_COST_TYPE_V.qvd` | CST_ITEM_COST_TYPE_V |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.GL_ITEM_CST.qvd` | GL_ITEM_CST |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/apps.HR_ALL_ORGANIZATION_UNITS.qvd` | HR_ALL_ORGANIZATION_UNITS |
| `3_Data_Repository/Oracle_EBS/INV.MTL_PARAMETERS.qvd` | MTL_PARAMETERS |
| `3_Data_Repository/Oracle_EBS/apps.mtl_planners.qvd` | MTL_PLANNERS |
| `3_Data_Repository/Oracle_EBS/apps.fnd_user.qvd` | FND_USER |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/po.po_req_distributions_all.qvd` | PO_REQ_DISTRIBUTIONS_ALL |
| `3_Data_Oracle_EBS/Materials Management/Purchasing/po.po_requisition_lines_all.qvd` | PO_REQUISITION_LINES_ALL |
| `3_Data_Oracle_EBS/Sales and Distribution/Sales Documents/apps.PO_REQUISITION_HEADERS_ALL.qvd` | PO_REQUISITION_HEADERS_ALL |

---

## Mapping Tables

| Map Name | Source | Key → Value |
|---|---|---|
| `OrgCode_Map` | MTL_PARAMETERS | ORGANIZATION_ID → ORGANIZATION_CODE |
| `ProcessFlagMap` | MTL_PARAMETERS | ORGANIZATION_ID → PROCESS_ENABLED_FLAG |
| `PlannerMap` | MTL_PLANNERS | ORG_ID-PLANNER_CODE → DESCRIPTION |
| `MRPPlanningCode_Map` | Inline | Lookup code → Meaning (MRP/MPS/Not planned/etc.) |
| `Release_map` | PO_RELEASES_ALL | PO_RELEASE_ID → RELEASE_NUM |
| `User_map` | FND_USER | USER_ID → USER_NAME |

---

## Row Counts (from Reload Log — May 24, 2026)

| Table/Map | Rows |
|---|---|
| OrgCode_Map | 138 |
| ProcessFlagMap | 138 |
| PlannerMap | 5,388 |
| MRPPlanningCode_Map | 6 |
| Release_map | 550,200 |
| User_map | 134,963 |
| sup (AP_SUPPLIERS) | 92,111 |
| ssite (AP_SUPPLIER_SITES_ALL) | 146,412 |

---

## Filters & Business Rules

1. **RCV Transactions** — filtered to `TRANSACTION_TYPE = 'RETURN TO VENDOR'` only
2. **Item Cost (CST_ITEM_COST_TYPE_V)** — filtered to `COST_TYPE_ID = 1` (Frozen Standard)
3. **Process Item Cost (GL_ITEM_CST)** — filtered to `COST_TYPE_ID = 1000`
4. **PO Rate** — NULL rates defaulted to 1: `if(IsNull(poh.RATE), 1, poh.RATE)`
5. **Blanket orders** — commented-out filter `Where Not match(poh.TYPE_LOOKUP_CODE,'BLANKET')` (currently loading ALL types)

---

## Key Dimensions & Measures for Migration

### Dimensions
- SUPPLIER, SUPPLIER_NUMBER, SITE (supplier site code)
- PO_NUMBER, LINE_NUM, SHIPMENT_NUM, DISTRIBUTION_NUM
- AUTHORIZATION_STATUS, TYPE_LOOKUP_CODE, DOC_CREATION_METHOD
- CURRENCY, OPERATING_UNIT
- Org Code, ORGANIZATION_NAME
- ITEM, ITEM_DESCRIPTION, Part_Number
- Planner, Process_Enabled_Flag
- pav.BUYER
- REQUISITION_NUM
- NEED_BY_DATE, PROMISED_DATE

### Measures
- TOTAL_SHIPMENT_AMT (ordered value in base currency)
- DOLLAR_AMT_RCVD (received value)
- DOLLAR_AMT_OPEN (open value)
- STANDARD_COST (frozen item cost)
- QUANTITY_ORDERED, QUANTITY_DELIVERED, QUANTITY_BILLED, QUANTITY_CANCELLED
- UNIT_PRICE

---

## Databricks Migration Mapping

| Qlik QVD Source | Databricks Target Table |
|---|---|
| apps.ap_suppliers | `mde_dev.stg_oracle_ebs.ap_suppliers` |
| apps.ap_supplier_sites_all | `mde_dev.stg_oracle_ebs.ap_supplier_sites_all` |
| apps.po_headers_all | `mde_dev.stg_oracle_ebs.po_headers_all` |
| apps.po_line_locations_all | `mde_dev.stg_oracle_ebs.po_line_locations_all` |
| apps.po_lines_all | `mde_dev.stg_oracle_ebs.po_lines_all` |
| apps.po_distributions_all | `mde_dev.stg_oracle_ebs.po_distributions_all` |
| PO.RCV_Transactions | `mde_dev.stg_oracle_ebs.rcv_transactions` |
| PO.RCV_SHIPMENT_HEADERS | `mde_dev.stg_oracle_ebs.rcv_shipment_headers` |
| apps.po_agents_v | `mde_dev.stg_oracle_ebs.po_agents_v` |
| inv.mtl_system_items_b | `mde_dev.stg_oracle_ebs.mtl_system_items_b` |
| apps.CST_ITEM_COST_TYPE_V | `mde_dev.stg_oracle_ebs.cst_item_cost_type_v` |
| apps.GL_ITEM_CST | `mde_dev.stg_oracle_ebs.gl_item_cst` |
| apps.HR_ALL_ORGANIZATION_UNITS | `mde_dev.stg_oracle_ebs.hr_all_organization_units` |
| INV.MTL_PARAMETERS | `mde_dev.stg_oracle_ebs.mtl_parameters` |
| apps.mtl_planners | `mde_dev.stg_oracle_ebs.mtl_planners` |
| apps.fnd_user | `mde_dev.stg_oracle_ebs.fnd_user` |
| PO_RELEASES_ALL | `mde_dev.stg_oracle_ebs.po_releases_all` |
| po.po_req_distributions_all | `mde_dev.stg_oracle_ebs.po_req_distributions_all` |
| po.po_requisition_lines_all | `mde_dev.stg_oracle_ebs.po_requisition_lines_all` |
| apps.PO_REQUISITION_HEADERS_ALL | `mde_dev.stg_oracle_ebs.po_requisition_headers_all` |

> **Note:** Table names above are inferred from the `stg_oracle_ebs` schema convention. Validate actual table names exist before building migration SQL.

---

## Change History (from LoadScript comments)

| Change | Story/Ticket | Author | Notes |
|---|---|---|---|
| OrgCode_Map added | — | Kiran (12/11/2017) | Procurement Audit Dashboard |
| DOC_CREATION_METHOD, REQ chain (prd/prla/prha) | STRY0012108 | — | New tabs for requisition tracing |
| FULL_LEAD_TIME added to msi | STRY0013706 | Kiran | |
| MRP_PLANNING_CODE map | STRY0015513 | Obul | |
| PO COMMENTS field | — | Kiran (11 Oct 2018) | |
| QUANTITY_SHIPPED, QUANTITY_RECEIVED in plla | — | Kiran (Oct/Nov 2018) | |
| pol.CANCEL_FLAG | — | Kiran (VIP) | |
| RATE_TYPE, RATE_DATE, RATE in poh | INC0671231 | Kiran (19 Jun 2019) | Multi-currency support |
| RCV tab (Return to Vendor) | — | Kiran (11 Oct 2018) | |
| Release_map, User_map, rcv detail fields | — | Neelo (11/26) | Return details |
| Part_Number from prla | — | Kiran (11 Oct 2018) | |

---

## Migration Considerations

1. **Composite keys** — `ORGANIZATION_ID || '|' || INVENTORY_ITEM_ID` must be replicated as `CONCAT(org_id, '|', item_id)` or use proper surrogate keys
2. **Multi-currency** — PO amounts multiplied by RATE (defaulting NULL to 1). Verify FX rate handling in Databricks gold layer.
3. **Process vs Discrete manufacturing** — Two cost sources (CST_ITEM_COST_TYPE_V for discrete, GL_ITEM_CST for process) concatenated into one table
4. **RCV filter** — Only RETURN TO VENDOR transactions loaded; full receiving may be needed for complete procurement picture
5. **Blanket orders** — Currently included (filter commented out). Confirm business requirement.
6. **550K release records** — Release_map is large; consider JOIN vs MAP approach in SQL
7. **Requisition chain** — pda → prd → prla → prha provides full req-to-PO traceability
8. **NEXUS Agent 88-95** (Qlik Migration agents) — can leverage this doc for automated conversion

---

## NEXUS Integration

This document feeds **Agent 88 (Qlik Migration Orchestrator)** and related agents 89-95 in the W1 Production Agents folder. The data model, source mappings, and business rules above provide the complete specification for automated Databricks SQL/metric view generation.

---

*Generated: July 30, 2026 | Source: `/5 - Personal Projects/7 - Qlik Migration/4.4.1 Procurement Analytics/`*
