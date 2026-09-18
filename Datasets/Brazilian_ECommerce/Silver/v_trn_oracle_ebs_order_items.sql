-- Databricks notebook source
CREATE OR REPLACE VIEW brazilian_ecommerce.silver.v_trn_oracle_ebs_order_items
AS 
SELECT
  order_id,
  order_item_id,
  product_id,
  seller_id,
  cast(shipping_limit_date as DATE) as shipping_limit_date,
  price,
  freight_value
FROM brazilian_ecommerce.raw.olist_order_items
where dl_iscurrent='True'
;