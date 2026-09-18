-- Databricks notebook source
CREATE OR REPLACE VIEW brazilian_ecommerce.silver.v_mst_oracle_ebs_olist_sellers
AS 
SELECT
  seller_id,
  seller_zip_code_prefix,
  INITCAP(seller_city)AS seller_city,
  seller_state
FROM brazilian_ecommerce.raw.olist_sellers
where dl_iscurrent = true
;