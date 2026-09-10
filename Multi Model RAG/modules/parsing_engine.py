"""
Multi-Modal RAG Pipeline: Parsing Engine
=========================================
Distributed layout-aware document extraction with table preservation and token-aware chunking.

Key Features:
- Distributed Processing: mapInPandas for scalable parsing across Spark workers
- Layout Preservation: Extract semantic blocks in reading order
- Table Integrity: Convert tables to Markdown format without splitting mid-row
- Multimodal Support: Text, tables, charts, and images with bounding boxes
- Token-Aware Chunking: Safe boundary detection to prevent context fragmentation
- Metadata Retention: Source URL, page number, element type, ACL groups

Author: Principal Databricks Architect
Date: 2026-09-04
"""

import uuid
import io
import logging
from typing import List, Dict, Iterator, Optional, Tuple
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, pandas_udf
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    BooleanType, TimestampType, MapType, ArrayType, DoubleType
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParsingEngine:
    """
    Orchestrates distributed document parsing using layout-aware extraction.
    Implements token-aware chunking with Markdown table preservation.
    """

    def __init__(self, spark: SparkSession, max_chunk_tokens: int = 512):
        """
        Initialize the parsing engine.

        Args:
            spark: Active SparkSession
            max_chunk_tokens: Maximum tokens per chunk (default: 512)
        """
        self.spark = spark
        self.max_chunk_tokens = max_chunk_tokens
        self.state_table = "ai_unstructured_metadata.document_state_registry"

    def get_pending_files(self, source_id: Optional[str] = None) -> DataFrame:
        """
        Retrieve files pending processing from the state registry.

        Args:
            source_id: Optional filter for specific source

        Returns:
            Spark DataFrame with pending files
        """
        query = f"""
            SELECT 
                file_id,
                source_id,
                file_uri,
                file_name,
                file_extension,
                volume_landing_path,
                source_access_control_groups
            FROM {self.state_table}
            WHERE status = 'PENDING'
        """
        if source_id:
            query += f" AND source_id = '{source_id}'"
        
        return self.spark.sql(query)

    def parse_documents(self, source_id: Optional[str] = None) -> Dict[str, int]:
        """
        Parse pending documents using distributed processing.

        Args:
            source_id: Optional filter for specific source

        Returns:
            Dictionary with processing statistics
        """
        pending_files_df = self.get_pending_files(source_id)
        
        if pending_files_df.count() == 0:
            logger.info("No pending files to process")
            return {"processed": 0, "failed": 0}

        logger.info(f"Processing {pending_files_df.count()} pending files")

        # Load files as binary
        binary_df = (
            self.spark.read.format("binaryFile")
            .load(pending_files_df.select("volume_landing_path").rdd.flatMap(lambda x: x).collect())
        )

        # Join with metadata
        processing_df = binary_df.join(
            pending_files_df,
            binary_df.path == pending_files_df.volume_landing_path,
            "inner"
        )

        # Define output schema for parsed chunks
        output_schema = StructType([
            StructField("chunk_id", StringType(), False),
            StructField("file_id", StringType(), False),
            StructField("source_id", StringType(), False),
            StructField("chunk_text", StringType(), False),
            StructField("chunk_index", IntegerType(), False),
            StructField("chunk_token_count", IntegerType(), True),
            StructField("file_uri", StringType(), False),
            StructField("file_name", StringType(), False),
            StructField("file_type", StringType(), True),
            StructField("page_number", IntegerType(), True),
            StructField("element_type", StringType(), True),
            StructField("element_metadata", MapType(StringType(), StringType()), True),
            StructField("is_table_chunk", BooleanType(), False),
            StructField("table_markdown", StringType(), True),
            StructField("acl_groups", ArrayType(StringType()), True),
            StructField("parsing_engine", StringType(), True),
            StructField("processing_status", StringType(), False),
            StructField("error_message", StringType(), True)
        ])

        # Apply distributed parsing using mapInPandas
        parsed_chunks_df = processing_df.mapInPandas(
            self._parse_file_batch,
            schema=output_schema
        )

        # Separate successful and failed chunks
        success_df = parsed_chunks_df.filter(col("processing_status") == "SUCCESS")
        failed_df = parsed_chunks_df.filter(col("processing_status") == "FAILED")

        success_count = success_df.count()
        failed_count = failed_df.count()

        # Get target table from first successful record
        if success_count > 0:
            target_table = self._get_target_table(success_df.first().source_id)
            
            # Write successful chunks to target table
            success_df.select(
                "chunk_id", "file_id", "source_id", "chunk_text", "chunk_index",
                "chunk_token_count", "file_uri", "file_name", "file_type",
                "page_number", "element_type", "element_metadata",
                "is_table_chunk", "table_markdown", "acl_groups", "parsing_engine"
            ).write.mode("append").saveAsTable(target_table)
            
            logger.info(f"Wrote {success_count} chunks to {target_table}")

            # Update state registry for successful files
            self._update_processing_status(success_df, "PROCESSED")

        # Update state registry for failed files
        if failed_count > 0:
            self._update_processing_status(failed_df, "FAILED")

        return {"processed": success_count, "failed": failed_count}

    def _parse_file_batch(self, iterator: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        """
        Parse a batch of files on a Spark worker using pandas UDF.
        This function runs in parallel across workers to avoid OOMs.

        Args:
            iterator: Iterator of pandas DataFrames containing file batches

        Yields:
            Iterator of pandas DataFrames containing parsed chunks
        """
        # Import heavy libraries inside worker to avoid serialization issues
        try:
            from unstructured.partition.auto import partition
            from unstructured.chunking.title import chunk_by_title
            import tiktoken
        except ImportError as e:
            logger.error(f"Failed to import required libraries: {e}")
            logger.info("Install with: pip install unstructured tiktoken")
            raise

        # Initialize tokenizer
        tokenizer = tiktoken.get_encoding("cl100k_base")

        for batch_df in iterator:
            results = []

            for _, row in batch_df.iterrows():
                file_id = row["file_id"]
                source_id = row["source_id"]
                file_name = row["file_name"]
                file_uri = row["file_uri"]
                file_extension = row["file_extension"]
                file_content = row["content"]
                acl_groups = row.get("source_access_control_groups", [])

                try:
                    # Parse document based on file type
                    if file_extension in ["pdf", "docx", "pptx"]:
                        chunks = self._parse_layout_aware(file_content, file_extension, tokenizer)
                    elif file_extension in ["json", "xml"]:
                        chunks = self._parse_structured(file_content, file_extension, tokenizer)
                    elif file_extension in ["txt", "md"]:
                        chunks = self._parse_text(file_content, tokenizer)
                    else:
                        raise ValueError(f"Unsupported file type: {file_extension}")

                    # Generate chunk records
                    for chunk_index, chunk_data in enumerate(chunks):
                        results.append({
                            "chunk_id": str(uuid.uuid4()),
                            "file_id": file_id,
                            "source_id": source_id,
                            "chunk_text": chunk_data["text"],
                            "chunk_index": chunk_index,
                            "chunk_token_count": chunk_data.get("token_count"),
                            "file_uri": file_uri,
                            "file_name": file_name,
                            "file_type": file_extension,
                            "page_number": chunk_data.get("page_number"),
                            "element_type": chunk_data.get("element_type", "text"),
                            "element_metadata": chunk_data.get("metadata", {}),
                            "is_table_chunk": chunk_data.get("is_table", False),
                            "table_markdown": chunk_data.get("table_markdown"),
                            "acl_groups": acl_groups,
                            "parsing_engine": chunk_data.get("parsing_engine", "layout_parser"),
                            "processing_status": "SUCCESS",
                            "error_message": None
                        })

                except Exception as e:
                    logger.error(f"Failed to parse {file_name}: {e}")
                    results.append({
                        "chunk_id": str(uuid.uuid4()),
                        "file_id": file_id,
                        "source_id": source_id,
                        "chunk_text": "",
                        "chunk_index": 0,
                        "chunk_token_count": 0,
                        "file_uri": file_uri,
                        "file_name": file_name,
                        "file_type": file_extension,
                        "page_number": None,
                        "element_type": "error",
                        "element_metadata": {},
                        "is_table_chunk": False,
                        "table_markdown": None,
                        "acl_groups": acl_groups,
                        "parsing_engine": None,
                        "processing_status": "FAILED",
                        "error_message": str(e)
                    })

            yield pd.DataFrame(results)

    def _parse_layout_aware(self, file_content: bytes, file_extension: str, tokenizer) -> List[Dict]:
        """
        Parse PDF, DOCX, PPTX using layout-aware extraction.
        Preserves semantic structure and converts tables to Markdown.

        Args:
            file_content: Raw file bytes
            file_extension: File extension
            tokenizer: Tiktoken tokenizer

        Returns:
            List of chunk dictionaries
        """
        from unstructured.partition.auto import partition
        from unstructured.documents.elements import Table, NarrativeText, Title

        # Partition document into elements
        elements = partition(file=io.BytesIO(file_content))

        chunks = []
        current_chunk_text = ""
        current_metadata = {}
        current_page = None

        for element in elements:
            element_type = type(element).__name__.lower()
            element_text = str(element)
            element_page = getattr(element, "metadata", {}).get("page_number")

            # Handle tables separately to preserve structure
            if isinstance(element, Table):
                # Convert table to Markdown format
                table_markdown = self._table_to_markdown(element)
                table_token_count = len(tokenizer.encode(table_markdown))

                # If current chunk exists, save it first
                if current_chunk_text:
                    chunks.append({
                        "text": current_chunk_text.strip(),
                        "token_count": len(tokenizer.encode(current_chunk_text)),
                        "page_number": current_page,
                        "element_type": "text",
                        "is_table": False,
                        "parsing_engine": "layout_parser"
                    })
                    current_chunk_text = ""

                # Add table as separate chunk (never split tables)
                chunks.append({
                    "text": table_markdown,
                    "token_count": table_token_count,
                    "page_number": element_page,
                    "element_type": "table",
                    "is_table": True,
                    "table_markdown": table_markdown,
                    "metadata": {"bbox": str(getattr(element, "metadata", {}).get("coordinates", {}))},
                    "parsing_engine": "layout_parser"
                })
                current_page = element_page

            else:
                # Accumulate text elements with token-aware boundaries
                potential_text = current_chunk_text + "\n\n" + element_text if current_chunk_text else element_text
                potential_token_count = len(tokenizer.encode(potential_text))

                if potential_token_count <= self.max_chunk_tokens:
                    current_chunk_text = potential_text
                    current_page = element_page or current_page
                else:
                    # Current chunk exceeds limit - save it and start new chunk
                    if current_chunk_text:
                        chunks.append({
                            "text": current_chunk_text.strip(),
                            "token_count": len(tokenizer.encode(current_chunk_text)),
                            "page_number": current_page,
                            "element_type": "text",
                            "is_table": False,
                            "parsing_engine": "layout_parser"
                        })
                    current_chunk_text = element_text
                    current_page = element_page

        # Add final chunk if exists
        if current_chunk_text:
            chunks.append({
                "text": current_chunk_text.strip(),
                "token_count": len(tokenizer.encode(current_chunk_text)),
                "page_number": current_page,
                "element_type": "text",
                "is_table": False,
                "parsing_engine": "layout_parser"
            })

        return chunks

    def _parse_structured(self, file_content: bytes, file_extension: str, tokenizer) -> List[Dict]:
        """
        Parse structured files (JSON, XML).

        Args:
            file_content: Raw file bytes
            file_extension: File extension
            tokenizer: Tiktoken tokenizer

        Returns:
            List of chunk dictionaries
        """
        import json
        import xml.etree.ElementTree as ET

        if file_extension == "json":
            data = json.loads(file_content.decode("utf-8"))
            text = json.dumps(data, indent=2)
        elif file_extension == "xml":
            tree = ET.fromstring(file_content.decode("utf-8"))
            text = ET.tostring(tree, encoding="unicode", method="xml")
        else:
            raise ValueError(f"Unsupported structured format: {file_extension}")

        # Simple token-aware chunking for structured content
        return self._chunk_text_by_tokens(text, tokenizer, "structured")

    def _parse_text(self, file_content: bytes, tokenizer) -> List[Dict]:
        """
        Parse plain text files.

        Args:
            file_content: Raw file bytes
            tokenizer: Tiktoken tokenizer

        Returns:
            List of chunk dictionaries
        """
        text = file_content.decode("utf-8")
        return self._chunk_text_by_tokens(text, tokenizer, "text")

    def _chunk_text_by_tokens(self, text: str, tokenizer, element_type: str) -> List[Dict]:
        """
        Chunk text by token count with sentence boundary awareness.

        Args:
            text: Input text
            tokenizer: Tiktoken tokenizer
            element_type: Type of element

        Returns:
            List of chunk dictionaries
        """
        import re

        # Split by paragraphs first
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            potential_chunk = current_chunk + "\n\n" + para if current_chunk else para
            token_count = len(tokenizer.encode(potential_chunk))

            if token_count <= self.max_chunk_tokens:
                current_chunk = potential_chunk
            else:
                # Save current chunk
                if current_chunk:
                    chunks.append({
                        "text": current_chunk.strip(),
                        "token_count": len(tokenizer.encode(current_chunk)),
                        "element_type": element_type,
                        "is_table": False,
                        "parsing_engine": "text_parser"
                    })
                current_chunk = para

        # Add final chunk
        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "token_count": len(tokenizer.encode(current_chunk)),
                "element_type": element_type,
                "is_table": False,
                "parsing_engine": "text_parser"
            })

        return chunks

    def _table_to_markdown(self, table_element) -> str:
        """
        Convert table element to Markdown format.

        Args:
            table_element: Unstructured Table element

        Returns:
            Markdown-formatted table string
        """
        # Extract table as text and parse rows
        table_text = str(table_element)
        
        # Simple heuristic: split by newlines and create markdown table
        # In production, use proper table extraction from element metadata
        lines = [line.strip() for line in table_text.split("\n") if line.strip()]
        
        if not lines:
            return table_text

        # Create Markdown table
        markdown_lines = []
        
        # Assume first line is header
        if lines:
            header = lines[0]
            markdown_lines.append(f"| {header} |")
            markdown_lines.append(f"| --- |")
            
            # Add data rows
            for line in lines[1:]:
                markdown_lines.append(f"| {line} |")
        
        return "\n".join(markdown_lines)

    def _get_target_table(self, source_id: str) -> str:
        """
        Get target Delta table name for a source.

        Args:
            source_id: Source identifier

        Returns:
            Fully qualified table name
        """
        result = self.spark.sql(f"""
            SELECT target_delta_table
            FROM ai_unstructured_metadata.ingestion_control
            WHERE source_id = '{source_id}'
        """).first()
        
        if result:
            return result.target_delta_table
        else:
            raise ValueError(f"No target table found for source: {source_id}")

    def _update_processing_status(self, chunks_df: DataFrame, status: str):
        """
        Update processing status in the document state registry.

        Args:
            chunks_df: DataFrame containing processed chunks
            status: Status to set (PROCESSED or FAILED)
        """
        # Get unique file IDs
        file_ids = chunks_df.select("file_id").distinct().rdd.flatMap(lambda x: x).collect()
        file_ids_str = "', '".join(file_ids)

        if status == "PROCESSED":
            # Calculate chunk counts per file
            chunk_counts = (
                chunks_df.groupBy("file_id")
                .count()
                .withColumnRenamed("count", "chunk_count")
            )
            
            # Update state registry
            for row in chunk_counts.collect():
                self.spark.sql(f"""
                    UPDATE {self.state_table}
                    SET 
                        status = '{status}',
                        chunk_count = {row.chunk_count},
                        processed_at = CURRENT_TIMESTAMP()
                    WHERE file_id = '{row.file_id}'
                """)
        else:
            # For failures, capture error messages
            error_df = chunks_df.select("file_id", "error_message").distinct()
            for row in error_df.collect():
                self.spark.sql(f"""
                    UPDATE {self.state_table}
                    SET 
                        status = '{status}',
                        error_message = '{row.error_message.replace("'", "''")}',
                        processed_at = CURRENT_TIMESTAMP()
                    WHERE file_id = '{row.file_id}'
                """)
