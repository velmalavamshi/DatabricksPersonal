-- =====================================================================
-- Multi-Modal RAG Pipeline: Unity Catalog Metadata Schema
-- =====================================================================
-- Purpose: Create Unity Catalog schema and governance structures for
--          enterprise-grade multi-modal RAG data ingestion pipeline
-- Author: Principal Databricks Architect
-- Date: 2026-09-04
-- =====================================================================

-- Create the metadata schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS mde_dev.ai_unstructured_metadata
COMMENT 'Metadata control plane for multi-modal RAG document ingestion and processing';

-- Grant appropriate permissions (adjust as per your organization's governance)
-- GRANT USE SCHEMA ON SCHEMA ai_unstructured_metadata TO `account users`;
-- GRANT SELECT ON SCHEMA ai_unstructured_metadata TO `account users`;

-- -- Display confirmation
-- DESCRIBE SCHEMA EXTENDED ai_unstructured_metadata;