import os
from datetime import datetime, timezone

import boto3

from src.config import AWS_REGION, DOC_STATUS_TABLE, UPLOAD_PATH

_document_status = {}
_dynamodb_resource = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_table():
    global _dynamodb_resource

    if not DOC_STATUS_TABLE:
        return None

    if _dynamodb_resource is None:
        kwargs = {}
        if AWS_REGION:
            kwargs["region_name"] = AWS_REGION
        _dynamodb_resource = boto3.resource("dynamodb", **kwargs)

    return _dynamodb_resource.Table(DOC_STATUS_TABLE)


def create_document_record(doc_id: str, **fields) -> dict:
    record = {
        "doc_id": doc_id,
        "status": fields.get("status", "pending"),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    record.update({k: v for k, v in fields.items() if v is not None})
    return _save_record(doc_id, record)


def get_document_status(doc_id: str) -> dict:
    table = _get_table()
    if table is None:
        return _document_status.get(doc_id, {"error": "Document not found"})

    result = table.get_item(Key={"doc_id": doc_id})
    return result.get("Item", {"error": "Document not found"})


def update_document_status(doc_id: str, **fields) -> dict:
    current = get_document_status(doc_id)
    record = {"doc_id": doc_id}
    if "error" not in current:
        record.update(current)
    record.update({k: v for k, v in fields.items() if v is not None})
    record["updated_at"] = _utc_now()
    if "created_at" not in record:
        record["created_at"] = _utc_now()
    return _save_record(doc_id, record)


def delete_document_record(doc_id: str) -> None:
    table = _get_table()
    if table is None:
        _document_status.pop(doc_id, None)
        return

    table.delete_item(Key={"doc_id": doc_id})


def local_uploaded_file_path(doc_id: str, filename: str | None = None) -> str | None:
    if filename:
        filename = os.path.basename(filename)
        candidate = os.path.join(UPLOAD_PATH, doc_id, filename)
        if os.path.exists(candidate):
            return candidate

    doc_dir = os.path.join(UPLOAD_PATH, doc_id)
    if not os.path.exists(doc_dir):
        return None

    files = [name for name in os.listdir(doc_dir) if not name.startswith(".")]
    if not files:
        return None

    return os.path.join(doc_dir, files[0])


def _save_record(doc_id: str, record: dict) -> dict:
    table = _get_table()
    if table is None:
        _document_status[doc_id] = record
        return record

    table.put_item(Item=record)
    return record
