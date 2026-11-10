# NEXUS Medallion Catalog — Confirmed Production Objects
# Source: mde_dev.information_schema.columns — Last refreshed: 2026-07-20
# Gold: 449 canonical objects | Platinum: 135 canonical objects

## HOW TO USE THIS CATALOG
Use exact names below. Never guess or invent a table name.
For tables not listed, run: SHOW TABLES IN mde_dev.gold / SHOW TABLES IN mde_dev.platinum
Always check Platinum first — it's pre-aggregated and Power BI/Genie-ready.

## PLATINUM DIMS (always prefer for reporting)
  mde_dev.platinum.dim_contract_capture_item_list_plt
  mde_dev.platinum.dim_customer_idn_gpo_hierarchy_owned_by_plt
  mde_dev.platinum.dim_customersite_service_plt
  mde_dev.platinum.dim_end_of_life_plt
  mde_dev.platinum.dim_global_contract_categories_plt
  mde_dev.platinum.dim_item_cost_costcal_plt
  mde_dev.platinum.dim_item_plt
  mde_dev.platinum.dim_itemcost_usd_plt
  mde_dev.platinum.dim_rls_tande_plt
  mde_dev.platinum.dim_salesorder_inventory_analysis_plt
  mde_dev.platinum.dim_service_geography_plt
  mde_dev.platinum.dim_service_request_nocharge_plt
  mde_dev.platinum.dim_territorysite_adjustments_plt
  mde_dev.platinum.dim_territorysite_combined_plt
  mde_dev.platinum.dim_territorysite_service_contract_plt

## DOMAIN INDEX — Gold & Platinum by Business Function

### Financial — GL / Journal Entries (EBS)
  GOLD FACTS:    fact_journal_entry, fact_gl_balance, fact_gl_import_reference
  GOLD DIMS:     dim_gl_code, dim_gl_daily_rates, dim_finance_calendar, dim_hfm_accounts, dim_organization_gl_set_of_books, dim_fnd_flex_values_vl
  PLATINUM:      fact_journal_entry_global_revenue_plt, fact_journal_entry_intl_revenue_plt, fact_actuals_plan_pvm_plt, fact_pbcs_actuals_vs_plan_plt

### Accounts Payable (EBS)
  GOLD FACTS:    fact_ap_invoice, fact_ap_invoice_distribution, fact_ap_payment, fact_invoice_workflow
  GOLD DIMS:     dim_ap_invoice, dim_ap_payment_terms, dim_bank_account, dim_payment_method, dim_payment_term
  PLATINUM:      fact_ap_invoice_ap_plt, fact_ap_payment_ap_plt, fact_ap_invoice_distribution_global_revenue_plt

### Accounts Receivable / Revenue (EBS)
  GOLD FACTS:    fact_ar_invoice_distribution, fact_revenue_stated
  GOLD DIMS:     dim_ar_lookups, dim_ra_terms
  PLATINUM:      fact_revenue_monthly_plt, fact_revenue_combined_global_revenue_plt, fact_ar_invoice_distribution_global_revenue_plt, fact_revenue_tieout_global_revenue_plt

### Sales Orders (EBS + Salesforce)
  GOLD FACTS:    fact_sales_order, fact_order_line_adjustments, fact_return_line, fact_delivery_detail, fact_shipment_detail, fact_shipping_transactions, fact_territory_adjustments
  GOLD DIMS:     dim_customer_account, dim_customer_site, dim_customer_idn_gpo, dim_customer_idn_gpo_hierarchy, dim_order_type, dim_order_source, dim_sales_rep, dim_territory_roster
  PLATINUM:      fact_sales_order_global_plt, fact_sales_order_global_master_plt, fact_order_item_plt, fact_sales_order_surgical_plt, fact_ar_executive_order_flash_plt, fact_otif_plt, fact_deliverydetail_otif_plt, fact_backorderstatus_otif_plt

### Procurement / Purchase Orders (EBS)
  GOLD FACTS:    fact_purchase_order, fact_purchase_requisition
  GOLD DIMS:     dim_purchase_order, dim_vendor_site, dim_buying_group, dim_sourcing_rules
  PLATINUM:      fact_purchase_order_ap_plt, fact_pobasic_globaldispatch_plt

### Inventory & Warehouse (EBS + Koerber)
  GOLD FACTS:    fact_material_transaction, fact_onhand_detail, fact_move_order, fact_item_subinventory, fact_global_intransit, fact_scrap_mtl, fact_koerber_shipment_charge_level, fact_inventory_non_onhand_global_inventory, fact_wip_discrete, fact_wip_transaction, fact_wip_value_mfg, fact_wip_requirement_operation
  GOLD DIMS:     dim_item, dim_item_category, dim_item_cost, dim_item_revision, dim_mtl_sys_items, dim_sub_inventory, dim_inventory_location, dim_mtl_safety_stock
  PLATINUM:      fact_onhand_material_globaldispatch_plt, fact_inventory_global_inventory, fact_aggr_transaction_global_inventory, fact_material_transaction_global_revenue_plt, fact_intransit_globaldispatch_plt, fact_invaging_globaldispatch_plt, fact_moveorder_globaldispatch_plt, fact_subinve_globaldispatch_plt

### Manufacturing / OPM (EBS)
  GOLD FACTS:    fact_opm_batches, fact_opm_perpetual_wip, fact_opm_steps_oprn, fact_opm_stprsc, fact_maintenance_asset, fact_maintenance_plan
  GOLD DIMS:     dim_opm_formula, dim_component_item_opm_cost
  PLATINUM:      fact_batchview_globaldispatch_plt, fact_mfgdispatch_globaldispatch_plt

### Quality Management (Agile PLM + EBS)
  GOLD FACTS:    fact_collection_quality, fact_product_complaint, fact_corrective_action, fact_field_action, fact_rcc_complaints, fact_rcc_agile_complaints, fact_qcr_p2_p3, fact_psr_p2_p3, fact_capa, fact_general_regulatory_report, fact_agile_change_history, fact_agile_signoff, fact_agile_workflow_process, fact_tga_device_ae_report, fact_cv_md_report
  GOLD DIMS:     dim_quality_item, dim_quality_site, dim_quality_supplier, dim_quality_cause_code, dim_quality_defect_code, dim_capa_detail, dim_nce_detail, dim_corrective_action_department_bridge, dim_field_action_detail, dim_quality_product_hierarchy, dim_quality_calendar, dim_qms_reference
  PLATINUM:      fact_product_complaint_plt, fact_quality_capital_plt, fact_quality_consumable_plt, fact_quality_nce_plt, fact_collection_quality_nce_plt, fact_quality_supplier_copq_cost_plt, fact_quality_supplier_nce_rate_plt, fact_qc_globaldispatch_plt, fact_agile_signoff_global_plt

### Service, Contracts & Install Base (EBS + H1)
  GOLD FACTS:    fact_service_contract, fact_ebs_contract, fact_contract_installbase, fact_work_order, fact_work_order_line_item, fact_service_appointment, fact_bill_line_transaction, fact_bill_line_transactions_all, fact_servicecosts_combined, fact_servicecosts_workorders
  GOLD DIMS:     dim_service_request, dim_work_type, dim_entitlement, dim_installbase, dim_instance_statuses, dim_service_labor_travel_cost, dim_asset_activity
  PLATINUM:      fact_contracts_combined_plt, fact_service_contract_revenue_plt, fact_case_plt, fact_work_order_plt, fact_installbase_combined_plt

### Salesforce Health Cloud — H1
  GOLD FACTS:    fact_h1_opportunity, fact_h1_contract, fact_h1_case, fact_h1_complaints, fact_h1_asset, fact_h1_quote, fact_h1case, fact_h1order, fact_h1ordercase, fact_h1workorder, fact_h1serviceappointment, fact_h1productcomplaint, fact_h1productconsumption, fact_h1productrequest
  GOLD DIMS:     dim_h1_account_hierarchy, dim_h1_contact, dim_h1_product, dim_h1_record_type, dim_h1_service_geography, dim_h1_service_territory, dim_h1_site_location, dim_h1_user, dim_h1_warranty_term
  PLATINUM:      fact_case_plt, fact_sales_order_global_plt

### Employee / HCM (Oracle HCM Cloud)
  GOLD FACTS:    fact_employee_assignments, fact_headcount_budget_fcst, fact_globalpersonpvo
  GOLD DIMS:     dim_employee, dim_department_hierarchy, dim_assignment_status, dim_manager_spans_layers, dim_hr_all_organization_units
  PLATINUM:      fact_employee_headcount_monthly_plt

### Financial Planning / PBCS
  GOLD FACTS:    fact_pbcs_actuals, fact_pbcs_forecast, fact_forecast_daily
  GOLD DIMS:     dim_essbase_account, dim_essbase_owner, dim_oracle_budget, dim_finance_family
  PLATINUM:      fact_pbcs_actuals_vs_plan_plt, fact_forecast_surgical_plt

### Projects & Spend (Oracle Projects)
  GOLD FACTS:    fact_project_spend, fact_project_expenditure, fact_project_budget_fcst, fact_concur_expense
  GOLD DIMS:     dim_project_employee, dim_project_manager, dim_project_time, dim_latum_project, dim_pa_expenditure_type
  PLATINUM:      fact_project_spend_analytics, fact_journal_entry_travel_expense_plt, fact_revenue_travel_expenses_plt

### Supply Chain / ASCP
  GOLD FACTS:    fact_ascp_pln_po_order
  PLATINUM:      fact_ascp_po_pln_order_globaldispatch_plt, fact_safety_stock_global_dispatch_plt, fact_itemsample_globaldispatch_plt

### Asset Management
  GOLD FACTS:    fact_wip_discrete, fact_wip_value_mfg, fact_maintenance_asset
  GOLD DIMS:     dim_asset_activity
  PLATINUM:      fact_asset_plt, fact_asset_national_plt

## FULL GOLD FACT TABLE LIST (all canonical)
  mde_dev.gold.fact_agile_change_history
  mde_dev.gold.fact_agile_signoff
  mde_dev.gold.fact_agile_workflow_process
  mde_dev.gold.fact_ap_invoice
  mde_dev.gold.fact_ap_invoice_distribution
  mde_dev.gold.fact_ap_payment
  mde_dev.gold.fact_ar_invoice_distribution
  mde_dev.gold.fact_arc_complaints_predictions
  mde_dev.gold.fact_ascp_pln_po_order
  mde_dev.gold.fact_bill_line_transaction
  mde_dev.gold.fact_bill_line_transactions_all
  mde_dev.gold.fact_bridge_ap_payment
  mde_dev.gold.fact_collection_quality
  mde_dev.gold.fact_concur_expense
  mde_dev.gold.fact_contract_ebs_headers_and_lines
  mde_dev.gold.fact_contract_installbase
  mde_dev.gold.fact_contract_territorysite_assn
  mde_dev.gold.fact_corrective_action
  mde_dev.gold.fact_cv_md_report
  mde_dev.gold.fact_delivery_detail
  mde_dev.gold.fact_ebs_contract
  mde_dev.gold.fact_email_notification
  mde_dev.gold.fact_employee_assignments
  mde_dev.gold.fact_field_action
  mde_dev.gold.fact_forecast_daily
  mde_dev.gold.fact_general_regulatory_report
  mde_dev.gold.fact_gl_balance
  mde_dev.gold.fact_gl_import_reference
  mde_dev.gold.fact_global_intransit
  mde_dev.gold.fact_globalpersonpvo
  mde_dev.gold.fact_h1_asset
  mde_dev.gold.fact_h1_complaints
  mde_dev.gold.fact_h1_contract
  mde_dev.gold.fact_h1_opportunity
  mde_dev.gold.fact_h1_quote
  mde_dev.gold.fact_h1case
  mde_dev.gold.fact_h1order
  mde_dev.gold.fact_h1ordercase
  mde_dev.gold.fact_h1productcomplaint
  mde_dev.gold.fact_h1productconsumption
  mde_dev.gold.fact_h1productrequest
  mde_dev.gold.fact_h1quote
  mde_dev.gold.fact_h1serviceappointment
  mde_dev.gold.fact_h1workorder
  mde_dev.gold.fact_headcount_budget_fcst
  mde_dev.gold.fact_inventory_non_onhand_global_inventory
  mde_dev.gold.fact_invoice_workflow
  mde_dev.gold.fact_item_subinventory
  mde_dev.gold.fact_journal_entry
  mde_dev.gold.fact_koerber_shipment_charge_level
  mde_dev.gold.fact_maintenance_asset
  mde_dev.gold.fact_maintenance_plan
  mde_dev.gold.fact_material_transaction
  mde_dev.gold.fact_material_transaction_lots
  mde_dev.gold.fact_move_order
  mde_dev.gold.fact_mtl_transaction_lot_number
  mde_dev.gold.fact_mtl_transaction_lot_numbers
  mde_dev.gold.fact_onhand_detail
  mde_dev.gold.fact_opm_batches
  mde_dev.gold.fact_opm_perpetual_wip
  mde_dev.gold.fact_opm_steps_oprn
  mde_dev.gold.fact_opm_stprsc
  mde_dev.gold.fact_order_line_adjustments
  mde_dev.gold.fact_pbcs_actuals
  mde_dev.gold.fact_pbcs_forecast
  mde_dev.gold.fact_product_complaint
  mde_dev.gold.fact_product_consumed
  mde_dev.gold.fact_product_request
  mde_dev.gold.fact_product_request_line_item
  mde_dev.gold.fact_product_transfer
  mde_dev.gold.fact_project_budget_fcst
  mde_dev.gold.fact_project_expenditure
  mde_dev.gold.fact_project_spend
  mde_dev.gold.fact_psr_item_view
  mde_dev.gold.fact_psr_p2_p3
  mde_dev.gold.fact_purchase_order
  mde_dev.gold.fact_purchase_requisition
  mde_dev.gold.fact_qcr_p2_p3
  mde_dev.gold.fact_qp_listline_prices
  mde_dev.gold.fact_rcc_agile_complaints
  mde_dev.gold.fact_rcc_complaints
  mde_dev.gold.fact_rcc_complaints_predictions
  mde_dev.gold.fact_rcc_salesforce_complaints
  mde_dev.gold.fact_reportable_authority
  mde_dev.gold.fact_reportable_authority_product_complaint_bridge
  mde_dev.gold.fact_return_line
  mde_dev.gold.fact_revenue_stated
  mde_dev.gold.fact_safety_value
  mde_dev.gold.fact_sales_order
  mde_dev.gold.fact_sbqq_cost
  mde_dev.gold.fact_scrap_mtl
  mde_dev.gold.fact_service_appointment
  mde_dev.gold.fact_service_contract
  mde_dev.gold.fact_service_price
  mde_dev.gold.fact_servicecosts_combined
  mde_dev.gold.fact_servicecosts_debrief
  mde_dev.gold.fact_servicecosts_estimates
  mde_dev.gold.fact_servicecosts_h1order
  mde_dev.gold.fact_servicecosts_productconsumed
  mde_dev.gold.fact_servicecosts_workorders
  mde_dev.gold.fact_shipment_detail
  mde_dev.gold.fact_shipping_transactions
  mde_dev.gold.fact_territory_adjustments
  mde_dev.gold.fact_tga_device_ae_report
  mde_dev.gold.fact_warehouse_override_adjustments
  mde_dev.gold.fact_wip_discrete
  mde_dev.gold.fact_wip_requirement_operation
  mde_dev.gold.fact_wip_transaction
  mde_dev.gold.fact_wip_value_mfg
  mde_dev.gold.fact_work_order
  mde_dev.gold.fact_work_order_line_item

## FULL GOLD DIM TABLE LIST (all canonical)
  mde_dev.gold.dim_account_hierarchy
  mde_dev.gold.dim_accounting_class
  mde_dev.gold.dim_analytics_catalog
  mde_dev.gold.dim_ap_invoice
  mde_dev.gold.dim_ap_invoice_entry_error_category
  mde_dev.gold.dim_ap_invoice_workitem
  mde_dev.gold.dim_ap_payment_terms
  mde_dev.gold.dim_ar_lookups
  mde_dev.gold.dim_asl
  mde_dev.gold.dim_asset_activity
  mde_dev.gold.dim_assignment_status
  mde_dev.gold.dim_bank_account
  mde_dev.gold.dim_bill_of_distribution
  mde_dev.gold.dim_bom_inventory_component
  mde_dev.gold.dim_buying_group
  mde_dev.gold.dim_capa_detail
  mde_dev.gold.dim_carrier_drift_metrics
  mde_dev.gold.dim_carrier_profile_metrics
  mde_dev.gold.dim_collection_plan
  mde_dev.gold.dim_company_hierarchy
  mde_dev.gold.dim_component_item_opm_cost
  mde_dev.gold.dim_corrective_action_department_bridge
  mde_dev.gold.dim_corrective_action_division_bridge
  mde_dev.gold.dim_corrective_action_product_line_bridge
  mde_dev.gold.dim_corrective_action_quality_site_bridge
  mde_dev.gold.dim_corrective_action_supplier_bridge
  mde_dev.gold.dim_country_region
  mde_dev.gold.dim_currency
  mde_dev.gold.dim_cust_profile_amts
  mde_dev.gold.dim_customer_account
  mde_dev.gold.dim_customer_experience_country
  mde_dev.gold.dim_customer_idn_gpo
  mde_dev.gold.dim_customer_idn_gpo_hierarchy
  mde_dev.gold.dim_customer_idn_group
  mde_dev.gold.dim_customer_site
  mde_dev.gold.dim_department_hierarchy
  mde_dev.gold.dim_division_hierarchy
  mde_dev.gold.dim_ea_value
  mde_dev.gold.dim_employee
  mde_dev.gold.dim_entitlement
  mde_dev.gold.dim_essbase_account
  mde_dev.gold.dim_essbase_owner
  mde_dev.gold.dim_external_data_value
  mde_dev.gold.dim_field_action_detail
  mde_dev.gold.dim_field_action_division_bridge
  mde_dev.gold.dim_field_action_product_line_bridge
  mde_dev.gold.dim_field_action_quality_site_bridge
  mde_dev.gold.dim_finance_accounts_payable_reporting_parameter
  mde_dev.gold.dim_finance_calendar
  mde_dev.gold.dim_finance_family
  mde_dev.gold.dim_fnd_flex_values_vl
  mde_dev.gold.dim_fnd_lookup_values
  mde_dev.gold.dim_fnd_user
  mde_dev.gold.dim_fob_point
  mde_dev.gold.dim_freight_terms
  mde_dev.gold.dim_geography_hierarchy
  mde_dev.gold.dim_gl_code
  mde_dev.gold.dim_gl_daily_rates
  mde_dev.gold.dim_global_contract_categories
  mde_dev.gold.dim_global_inv_transaction_types
  mde_dev.gold.dim_global_inv_transaction_types
  mde_dev.gold.dim_h1_account_hierarchy
  mde_dev.gold.dim_h1_contact
  mde_dev.gold.dim_h1_product
  mde_dev.gold.dim_h1_product_source_division
  mde_dev.gold.dim_h1_record_type
  mde_dev.gold.dim_h1_service_geography
  mde_dev.gold.dim_h1_service_territory
  mde_dev.gold.dim_h1_site_location
  mde_dev.gold.dim_h1_user
  mde_dev.gold.dim_h1_warranty_term
  mde_dev.gold.dim_hfm_accounts
  mde_dev.gold.dim_hr_all_organization_units
  mde_dev.gold.dim_hz_code_assignments
  mde_dev.gold.dim_hz_cust_accounts
  mde_dev.gold.dim_hz_cust_acct_sites_all
  mde_dev.gold.dim_hz_cust_site_uses_all
  mde_dev.gold.dim_hz_locations
  mde_dev.gold.dim_hz_parties
  mde_dev.gold.dim_hz_party_sites
  mde_dev.gold.dim_installbase
  mde_dev.gold.dim_instance_statuses
  mde_dev.gold.dim_inventory_location
  mde_dev.gold.dim_inventory_type
  mde_dev.gold.dim_invoice_workflow
  mde_dev.gold.dim_item
  mde_dev.gold.dim_item_category
  mde_dev.gold.dim_item_cost
  mde_dev.gold.dim_item_cost_conversion_rate
  mde_dev.gold.dim_item_cost_historical
  mde_dev.gold.dim_item_lot
  mde_dev.gold.dim_item_revision
  mde_dev.gold.dim_latum_project
  mde_dev.gold.dim_manager_spans_layers
  mde_dev.gold.dim_mtl_safety_stock
  mde_dev.gold.dim_mtl_serial_number
  mde_dev.gold.dim_mtl_sys_items
  mde_dev.gold.dim_mtl_transaction_type
  mde_dev.gold.dim_nce_detail
  mde_dev.gold.dim_operating_unit
  mde_dev.gold.dim_opm_formula
  mde_dev.gold.dim_oracle_budget
  mde_dev.gold.dim_order_source
  mde_dev.gold.dim_order_type
  mde_dev.gold.dim_org_hierarchypvo
  mde_dev.gold.dim_organization_gl_set_of_books
  mde_dev.gold.dim_pa_expenditure_type
  mde_dev.gold.dim_payment_method
  mde_dev.gold.dim_payment_term
  mde_dev.gold.dim_payment_terms
  mde_dev.gold.dim_product_family
  mde_dev.gold.dim_product_hierarchy
  mde_dev.gold.dim_product_source_division
  mde_dev.gold.dim_project_employee
  mde_dev.gold.dim_project_finance_accounting
  mde_dev.gold.dim_project_manager
  mde_dev.gold.dim_project_time
  mde_dev.gold.dim_purchase_order
  mde_dev.gold.dim_qms_reference
  mde_dev.gold.dim_quality_calendar
  mde_dev.gold.dim_quality_cause_code
  mde_dev.gold.dim_quality_defect_code
  mde_dev.gold.dim_quality_department
  mde_dev.gold.dim_quality_division
  mde_dev.gold.dim_quality_item
  mde_dev.gold.dim_quality_kpi_goals
  mde_dev.gold.dim_quality_product_hierarchy
  mde_dev.gold.dim_quality_product_line
  mde_dev.gold.dim_quality_site
  mde_dev.gold.dim_quality_supplier
  mde_dev.gold.dim_quality_supplier_aux
  mde_dev.gold.dim_quality_system
  mde_dev.gold.dim_quality_user
  mde_dev.gold.dim_ra_terms
  mde_dev.gold.dim_sales_rep
  mde_dev.gold.dim_sales_workflow
  mde_dev.gold.dim_salesorder_inventory_analysis
  mde_dev.gold.dim_sbqq_cost
  mde_dev.gold.dim_section_access_external_data
  mde_dev.gold.dim_service_labor_travel_cost
  mde_dev.gold.dim_service_override_item_cost
  mde_dev.gold.dim_service_request
  mde_dev.gold.dim_sfx_rates_cy
  mde_dev.gold.dim_sfx_rates_py
  mde_dev.gold.dim_sfx_rates_usd
  mde_dev.gold.dim_silver_ref_corporate_finance_accounts_payable_reporting
  mde_dev.gold.dim_sourcing_rules
  mde_dev.gold.dim_standard_cost
  mde_dev.gold.dim_statement_line_hierarchy
  mde_dev.gold.dim_sub_inventory
  mde_dev.gold.dim_territory_outbound
  mde_dev.gold.dim_territory_roster
  mde_dev.gold.dim_territory_site_bridge
  mde_dev.gold.dim_territorysite_asset
  mde_dev.gold.dim_vendor_site
  mde_dev.gold.dim_work_type

## FULL PLATINUM FACT TABLE LIST (all canonical)
  mde_dev.platinum.fact_actuals_plan_pvm_plt
  mde_dev.platinum.fact_aggr_transaction_global_inventory
  mde_dev.platinum.fact_agile_signoff_global_plt
  mde_dev.platinum.fact_ap_invoice_ap_plt
  mde_dev.platinum.fact_ap_invoice_distribution_global_revenue_plt
  mde_dev.platinum.fact_ap_invoice_distribution_intl_revenue_plt
  mde_dev.platinum.fact_ap_payment_ap_plt
  mde_dev.platinum.fact_ar_executive_order_flash_plt
  mde_dev.platinum.fact_ar_invoice_distribution_global_revenue_plt
  mde_dev.platinum.fact_ar_invoice_distribution_intl_revenue_plt
  mde_dev.platinum.fact_ar_invoice_distribution_service_plt
  mde_dev.platinum.fact_ascp_po_pln_order_globaldispatch_plt
  mde_dev.platinum.fact_asset_national_plt
  mde_dev.platinum.fact_asset_plt
  mde_dev.platinum.fact_backorderstatus_otif_plt
  mde_dev.platinum.fact_batchview_globaldispatch_plt
  mde_dev.platinum.fact_case_plt
  mde_dev.platinum.fact_collection_quality_nce_plt
  mde_dev.platinum.fact_combined_adjustments_plt
  mde_dev.platinum.fact_contracts_combined_plt
  mde_dev.platinum.fact_deliverydetail_otif_plt
  mde_dev.platinum.fact_email_notification_aen_plt
  mde_dev.platinum.fact_employee_headcount_monthly_plt
  mde_dev.platinum.fact_forecast_surgical_plt
  mde_dev.platinum.fact_free_of_charge_account_plt
  mde_dev.platinum.fact_installbase_combined_plt
  mde_dev.platinum.fact_intransit_globaldispatch_plt
  mde_dev.platinum.fact_invaging_globaldispatch_plt
  mde_dev.platinum.fact_inventory_global_inventory
  mde_dev.platinum.fact_itemsample_globaldispatch_plt
  mde_dev.platinum.fact_journal_entry_global_revenue_plt
  mde_dev.platinum.fact_journal_entry_intl_revenue_plt
  mde_dev.platinum.fact_journal_entry_travel_expense_plt
  mde_dev.platinum.fact_material_transaction_global_revenue_plt
  mde_dev.platinum.fact_material_transaction_intl_revenue_plt
  mde_dev.platinum.fact_material_transaction_quality_plt
  mde_dev.platinum.fact_material_transaction_supply_chain_plt
  mde_dev.platinum.fact_mfgdispatch_globaldispatch_plt
  mde_dev.platinum.fact_moveorder_globaldispatch_plt
  mde_dev.platinum.fact_onhand_global_inv_plt
  mde_dev.platinum.fact_onhand_material_globaldispatch_plt
  mde_dev.platinum.fact_order_item_plt
  mde_dev.platinum.fact_otif_plt
  mde_dev.platinum.fact_otif_rootcauses_plt
  mde_dev.platinum.fact_pbcs_actuals_vs_plan_plt
  mde_dev.platinum.fact_pobasic_globaldispatch_plt
  mde_dev.platinum.fact_product_complaint_plt
  mde_dev.platinum.fact_product_consumed_plt
  mde_dev.platinum.fact_project_spend_analytics
  mde_dev.platinum.fact_purchase_order_ap_plt
  mde_dev.platinum.fact_qc_globaldispatch_plt
  mde_dev.platinum.fact_quality_capital_plt
  mde_dev.platinum.fact_quality_consumable_plt
  mde_dev.platinum.fact_quality_nce_plt
  mde_dev.platinum.fact_quality_supplier_copq_cost_plt
  mde_dev.platinum.fact_quality_supplier_nce_rate_plt
  mde_dev.platinum.fact_reportable_authority_plt
  mde_dev.platinum.fact_revenue_combined_global_revenue_plt
  mde_dev.platinum.fact_revenue_combined_intl_revenue_plt
  mde_dev.platinum.fact_revenue_global_revenue_plt
  mde_dev.platinum.fact_revenue_intl_revenue_plt
  mde_dev.platinum.fact_revenue_monthly_plt
  mde_dev.platinum.fact_revenue_stated_global_revenue_plt
  mde_dev.platinum.fact_revenue_tieout_global_revenue_plt
  mde_dev.platinum.fact_revenue_tieout_intl_revenue_plt
  mde_dev.platinum.fact_revenue_travel_expenses_plt
  mde_dev.platinum.fact_safety_kpi_value_plt
  mde_dev.platinum.fact_safety_stock_global_dispatch_plt
  mde_dev.platinum.fact_sales_adjustments_combined_plt
  mde_dev.platinum.fact_sales_adjustments_surgical_plt
  mde_dev.platinum.fact_sales_link_table_surgical_plt
  mde_dev.platinum.fact_sales_order_bsh_plt
  mde_dev.platinum.fact_sales_order_executive_order_flash_plt
  mde_dev.platinum.fact_sales_order_free_of_charge_plt
  mde_dev.platinum.fact_sales_order_global_master_plt
  mde_dev.platinum.fact_sales_order_global_plt
  mde_dev.platinum.fact_sales_order_global_revenue_plt
  mde_dev.platinum.fact_sales_order_intl_revenue_plt
  mde_dev.platinum.fact_sales_order_nocharge_plt
  mde_dev.platinum.fact_sales_order_open_global_revenue_plt
  mde_dev.platinum.fact_sales_order_open_intl_revenue_plt
  mde_dev.platinum.fact_sales_order_surgical_performance_plt
  mde_dev.platinum.fact_sales_order_surgical_plt
  mde_dev.platinum.fact_sales_values_plt
  mde_dev.platinum.fact_service_contract_revenue_plt
  mde_dev.platinum.fact_subinve_globaldispatch_plt
  mde_dev.platinum.fact_territory_adjustments
  mde_dev.platinum.fact_work_order_plt