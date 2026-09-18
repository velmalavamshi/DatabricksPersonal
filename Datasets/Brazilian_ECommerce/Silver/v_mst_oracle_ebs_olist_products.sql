-- Databricks notebook source
CREATE OR REPLACE VIEW brazilian_ecommerce.silver.v_mst_oracle_ebs_olist_products
AS 
SELECT
  product_id,
  initcap(product_category_name) as product_category_name,
  product_name_lenght,
  product_description_lenght,
  product_photos_qty,
  product_weight_g,
  product_length_cm,
  product_height_cm,
  product_width_cm
FROM brazilian_ecommerce.raw.olist_products
where dl_iscurrent = TRUE
;