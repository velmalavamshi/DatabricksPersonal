-- Databricks notebook source
CREATE OR REPLACE VIEW brazilian_ecommerce.silver.v_trn_oracle_ebs_olist_order_payments
AS 
SELECT distinct
  order_id,
  payment_sequential,
  initcap(payment_type)as payment_type,
  payment_installments,
  payment_value
FROM brazilian_ecommerce.raw.olist_order_payments
where dl_iscurrent = True
;