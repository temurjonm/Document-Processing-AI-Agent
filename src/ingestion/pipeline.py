import os
import tempfile

import boto3

from src.config import AWS_REGION, S3_BUCKET, UPLOAD_PATH
from src.ingestion.chunker import chunk_document
from src.ingestion.extractor import extract_text
from src.search.vector_store import VectorStore
from src.storage.document_store import update_document_status


def process_local_document(doc_id: str) -> dict:
    doc_dir = os.path.join(UPLOAD_PATH, doc_id)
    files = [f for f in os.listdir(doc_dir) if not f.startswith(".")] if os.path.exists(doc_dir) else []
    if not files:
        raise FileNotFoundError("Document not found — no file in uploads folder")

    file_path = os.path.join(doc_dir, files[0])
    return process_document_path(doc_id, file_path)


def process_s3_document(doc_id: str, s3_key: str, bucket: str | None = None) -> dict:
    target_bucket = bucket or S3_BUCKET
    if not target_bucket:
        raise ValueError("S3 bucket is not configured")

    with tempfile.TemporaryDirectory(prefix="doc-agent-") as tmp_dir:
        filename = os.path.basename(s3_key) or f"{doc_id}.bin"
        file_path = os.path.join(tmp_dir, filename)

        kwargs = {}
        if AWS_REGION:
            kwargs["region_name"] = AWS_REGION

        boto3.client("s3", **kwargs).download_file(target_bucket, s3_key, file_path)
        return process_document_path(doc_id, file_path)


def process_document_path(doc_id: str, file_path: str) -> dict:
    try:
        update_document_status(doc_id, status="processing")

        pages = extract_text(file_path)
        chunks = chunk_document(pages, doc_id)

        vector_store = VectorStore()
        vector_store.delete_document(doc_id)
        vector_store.add_chunks(chunks)

        result = {
            "doc_id": doc_id,
            "status": "ready",
            "pages": len(pages),
            "chunks": len(chunks),
        }
        update_document_status(
            doc_id,
            status="ready",
            page_count=len(pages),
            chunk_count=len(chunks),
        )
        return result
    except Exception as exc:
        update_document_status(doc_id, status="failed", error=str(exc))
        raise
