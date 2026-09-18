-- Databricks notebook source
create or replace table  brazilian_ecommerce.gold.dim_products
/*
TBLPROPERTIES (
  'config.nk_column_names' = 'product_id,order_id,seller_id,order_item_id',
  'config.cluster_by' = '',
  'config.fact_type' = 1,
  'config.sk_column_nane' = 'product_sk',
  'config.primary_key' = 'product_sk',
  'config.foreign_key' = '',
  'config.unique_constraints' = '',
  'config.not_null_constraints' = '',
  'config.check_constraints' = ''
)
as
*/
select 
md5(concat_ws('|',p.product_id,item.order_id,item.seller_id,item.order_item_id)) as product_sk, --Primary Key
  item.order_id,
  item.order_item_id,
  item.seller_id,
  p.product_id,
  item.shipping_limit_date,
  p.product_category_name,
  Initcap(pcn.product_category_name_english) as product_category_name_english,
  p.product_name_lenght,
  p.product_description_lenght,
  p.product_photos_qty,
  p.product_weight_g,
  p.product_length_cm,
  p.product_height_cm,
  p.product_width_cm
from  brazilian_ecommerce.silver.v_mst_oracle_ebs_olist_products p
inner join brazilian_ecommerce.silver.v_trn_oracle_ebs_order_items item
on p.product_id = item.product_id
left join brazilian_ecommerce.raw.product_category_name_translation pcn
on p.product_category_name = initcap(pcn.product_category_name)

-- COMMAND ----------

