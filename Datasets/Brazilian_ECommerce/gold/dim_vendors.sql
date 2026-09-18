-- Databricks notebook source
--create or replace table mde_dev.gold.dim_vendors
/*
TBLPROPERTIES (
  'config.nk_column_names' = '',
  'config.cluster_by' = 'seller_id,seller_zip_code_prefix,geolocation_zip_code_prefix',
  'config.fact_type' = 1,
  'config.sk_column_nane' = 'seller_sk',
  'config.primary_key' = 'seller_sk',
  'config.foreign_key' = '',
  'config.unique_constraints' = '',
  'config.not_null_constraints' = '',
  'config.check_constraints' = ''
)
*/
--as
--with temp as (
select
  md5(concat_ws('|',s.seller_id,s.seller_zip_code_prefix,gl.geolocation_zip_code_prefix)) as seller_sk, --Primary Key
  s.seller_id,
  s.seller_zip_code_prefix,
  s.seller_city,
  s.seller_state,
  gl.geolocation_zip_code_prefix,
  gl.geolocation_lat,
  gl.geolocation_lng,
  gl.geolocation_city,
  gl.geolocation_state
from mde_dev.silver.v_mst_raw_sellers s
inner join mde_dev.silver.v_mst_geolocation gl
  on s.seller_zip_code_prefix=gl.geolocation_zip_code_prefix)

/*
  select seller_id,seller_zip_code_prefix,geolocation_zip_code_prefix,count(*) from temp 
  where seller_id is null
  group by all
  having count(*)>1;
  */
  