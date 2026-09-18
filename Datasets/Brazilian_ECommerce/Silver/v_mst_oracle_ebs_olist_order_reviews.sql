-- Databricks notebook source
CREATE OR REPLACE VIEW brazilian_ecommerce.silver.v_mst_oracle_ebs_olist_order_reviews
AS 
SELECT
  review_id,
  order_id,
  review_score,
  review_comment_title,
  INITCAP(review_comment_message)AS review_comment_message,
  review_creation_date,
  review_answer_timestamp
FROM brazilian_ecommerce.raw.olist_order_reviews
where dl_iscurrent = true
;