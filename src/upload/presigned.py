# Handles file upload using the pre-signed URL pattern:
# 1. Client asks our API for an upload URL
# 2. Our API validates the request and generates a pre-signed S3 URL
# 3. Client uploads the file DIRECTLY to S3 (our server never touches the file)
# 4. S3 Event → SQS → Worker picks up the file for processing
#
# Why not just POST the file to our API?
# → Our server becomes a bottleneck. A 50MB file ties up a connection for 10+ seconds.
# → With pre-signed URLs, S3 handles the transfer. Our server just generates a URL in 50ms.
# → S3 is designed for file storage. Our API server is designed for request handling.

import os
import uuid  # for generating unique document IDs
import boto3  # AWS SDK — for generating pre-signed URLs
from src.config import (
    S3_BUCKET, UPLOAD_PATH, ALLOWED_TYPES,
    MAX_FILE_SIZE, PRESIGNED_URL_EXPIRY
)
from src.storage.document_store import (
    create_document_record,
    get_document_status,
    update_document_status,
)


def request_upload(filename: str, content_type: str, size_bytes: int) -> dict:
    """
    Validate the upload request and return a pre-signed URL (or local fallback).
    This is called by the POST /api/documents/request-upload endpoint.

    Args:
        filename: original filename (e.g., "contract.pdf")
        content_type: MIME type (e.g., "application/pdf")
        size_bytes: file size in bytes
    Returns:
        {doc_id, upload_url, method, expires_in} or raises ValueError
    """
    # ── Validate file type ──
    # Only allow PDF, DOCX, PNG, JPG — reject everything else
    if content_type not in ALLOWED_TYPES:
        raise ValueError(
            f"Unsupported file type: {content_type}. "
            f"Allowed: {', '.join(ALLOWED_TYPES)}"
        )

    # ── Validate file size ──
    # 50MB max — protects against accidental huge uploads
    if size_bytes > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)  # convert bytes to MB for error message
        raise ValueError(f"File too large. Maximum size: {max_mb}MB")

    # ── Generate a unique document ID ──
    doc_id = str(uuid.uuid4())

    # ── Generate the upload URL ──
    if S3_BUCKET:
        # Production mode: generate a real S3 pre-signed URL
        upload_info = _generate_s3_presigned_url(doc_id, filename, content_type)
        create_document_record(
            doc_id,
            status="pending",
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            page_count=0,
            chunk_count=0,
            storage_backend="s3",
            s3_bucket=S3_BUCKET,
            s3_key=upload_info["s3_key"],
        )
    else:
        # Local dev mode: return a local upload endpoint
        # Create the directory for this document's files
        doc_dir = os.path.join(UPLOAD_PATH, doc_id)
        os.makedirs(doc_dir, exist_ok=True)  # exist_ok prevents error if already exists

        upload_info = {
            "upload_url": f"/api/documents/{doc_id}/upload-local",
            "method": "POST",  # local uploads use POST with multipart form
            "expires_in": None  # local URLs don't expire
        }
        create_document_record(
            doc_id,
            status="pending",
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            page_count=0,
            chunk_count=0,
            storage_backend="local",
        )

    return {
        "doc_id": doc_id,
        **upload_info  # spread the upload URL and method into the response
    }


def _generate_s3_presigned_url(doc_id: str, filename: str, content_type: str) -> dict:
    """
    Generate a pre-signed S3 PUT URL.
    The client uses this URL to upload directly to S3 via HTTP PUT.

    The URL is:
    - Time-limited (15 minutes) — can't be reused after expiry
    - Scoped to a specific S3 key — can't upload to a different path
    - Content-type locked — can't upload a different file type
    """
    # Create an S3 client using boto3
    s3_client = boto3.client("s3")

    # The S3 key (path) where the file will be stored
    # Format: documents/{doc_id}/{filename}
    s3_key = f"documents/{doc_id}/{filename}"

    # generate_presigned_url creates a signed URL that allows a PUT request
    # Anyone with this URL can upload to this specific S3 key (and only this key)
    presigned_url = s3_client.generate_presigned_url(
        "put_object",  # the S3 operation this URL will allow
        Params={
            "Bucket": S3_BUCKET,           # which S3 bucket
            "Key": s3_key,                 # the file path in S3
            "ContentType": content_type     # lock the content type
        },
        ExpiresIn=PRESIGNED_URL_EXPIRY  # URL valid for 15 minutes
    )

    return {
        "upload_url": presigned_url,
        "method": "PUT",         # S3 pre-signed URLs use PUT, not POST
        "expires_in": PRESIGNED_URL_EXPIRY,
        "s3_key": s3_key
    }


def save_local_upload(doc_id: str, file_content: bytes, filename: str) -> str:
    """
    Save a file locally (development mode only).
    In production, files go to S3 via pre-signed URL, never through our server.

    Returns: the local file path where the file was saved
    """
    doc_dir = os.path.join(UPLOAD_PATH, doc_id)
    os.makedirs(doc_dir, exist_ok=True)

    # Fallback if filename is None or empty (e.g., Swagger UI upload)
    # Try to get the original filename from the status tracker
    if not filename:
        status = get_document_status(doc_id)
        filename = status.get("filename", "uploaded_file.pdf")

    # Sanitise filename to prevent path traversal
    filename = os.path.basename(filename)
    file_path = os.path.join(doc_dir, filename)
    with open(file_path, "wb") as f:  # "wb" = write bytes (not text)
        f.write(file_content)

    return file_path
