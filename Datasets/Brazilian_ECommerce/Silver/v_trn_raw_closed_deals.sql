-- Databricks notebook source
CREATE OR REPLACE VIEW mde_dev.silver.v_trn_raw_closed_deals
AS 
SELECT
  mql_id,
  seller_id,
  sdr_id,
  sr_id,
  CAST(won_date AS DATE)AS won_date,
  INITCAP(business_segment) AS business_segment,
  INITCAP(lead_type)AS lead_type,
  INITCAP(lead_behaviour_profile)AS lead_behaviour_profile,
  has_company,
  has_gtin,
  average_stock,
  INITCAP(business_type)AS business_type,
  declared_product_catalog_size,
  declared_monthly_revenue
FROM MDE_DEV.RAW.closed_deals;