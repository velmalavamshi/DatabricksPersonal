-- Databricks notebook source
CREATE OR REPLACE VIEW mde_dev.silver.v_mst_raw_marketing
AS 
SELECT
  mql_id,
  cast(first_contact_date as DATE)as first_contact_date,
  landing_page_id,
  initcap(origin)as origin
FROM mde_dev.raw.marketing
;