import json
import logging
import time
from urllib.parse import unquote_plus

import boto3

from src.config import AWS_REGION, INGESTION_QUEUE_URL, WORKER_MAX_MESSAGES, WORKER_POLL_WAIT_SECONDS
from src.ingestion.pipeline import process_s3_document
from src.storage.document_store import update_document_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _sqs_client():
    kwargs = {}
    if AWS_REGION:
        kwargs["region_name"] = AWS_REGION
    return boto3.client("sqs", **kwargs)


def _parse_s3_records(message_body: str) -> list[tuple[str, str, str]]:
    payload = json.loads(message_body)
    records = payload.get("Records", [])
    parsed = []
    for record in records:
        if record.get("eventSource") != "aws:s3":
            continue

        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        parts = key.split("/", 2)
        if len(parts) < 3 or parts[0] != "documents":
            continue

        parsed.append((parts[1], bucket, key))

    return parsed


def main() -> None:
    if not INGESTION_QUEUE_URL:
        raise SystemExit("INGESTION_QUEUE_URL is not configured")

    client = _sqs_client()
    logger.info("Starting SQS worker")

    while True:
        response = client.receive_message(
            QueueUrl=INGESTION_QUEUE_URL,
            MaxNumberOfMessages=WORKER_MAX_MESSAGES,
            WaitTimeSeconds=WORKER_POLL_WAIT_SECONDS,
            VisibilityTimeout=300,
        )

        messages = response.get("Messages", [])
        if not messages:
            continue

        for message in messages:
            receipt_handle = message["ReceiptHandle"]
            try:
                records = _parse_s3_records(message["Body"])
                for doc_id, bucket, key in records:
                    logger.info("Processing %s from %s", doc_id, key)
                    update_document_status(doc_id, status="uploaded", s3_bucket=bucket, s3_key=key)
                    process_s3_document(doc_id, key, bucket=bucket)
                client.delete_message(QueueUrl=INGESTION_QUEUE_URL, ReceiptHandle=receipt_handle)
            except Exception as exc:
                logger.exception("Worker failed: %s", exc)
                time.sleep(2)


if __name__ == "__main__":
    main()
