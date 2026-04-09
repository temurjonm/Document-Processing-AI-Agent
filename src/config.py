"""
config.py — Central configuration for the entire app.

WHY THIS FILE EXISTS:
- All settings in one place, not scattered across files
- Environment variables loaded once, validated at startup
- Easy to switch between local dev and production
"""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Embedding Settings
# text-embedding-3-small: cheapest OpenAI embedding model
# 1536 dimensions is its output size — each text becomes a 1536-number vector
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # fixed by the model, you can't change this
EMBEDDING_BATCH_SIZE = 100   # send 100 texts per API call (max is 2048, but 100 is safer)

# Chunking Settings
CHUNK_SIZE = 500         # tokens per chunk — sweet spot for document processing
CHUNK_OVERLAP = 50       # overlap tokens — ensures context continuity at boundaries

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]  # recursive split order: sections → paragraphs → sentences → words

# Hybrid Search
DENSE_WEIGHT = 0.7       # semantic similarity weight
BM25_WEIGHT = 0.3        # keyword matching weight — catches exact terms (names, IDs, dates)
TOP_K = 5                # number of results to return

# LLM Models
SIMPLE_MODEL = "gpt-4o-mini"    # $0.15 per million tokens — use for 70% of queries
COMPLEX_MODEL = "gpt-4o"        # $2.50 per million tokens — use for 30% of queries

# Agent Settings
MAX_AGENT_ITERATIONS = 5   # prevent infinite loops
AGENT_TIMEOUT_SECONDS = 30
MAX_TOKENS_PER_SESSION = 10000

# Upload Settings
# File types we accept — anything else gets rejected at the API level
ALLOWED_TYPES = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "image/png", "image/jpeg"]
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB in bytes — protects against huge uploads

# AWS Settings
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", ""))
DOC_STATUS_TABLE = os.getenv("DOC_STATUS_TABLE", "")
INGESTION_QUEUE_URL = os.getenv("INGESTION_QUEUE_URL", "")

# Storage Paths
CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")   # where ChromaDB saves vectors
UPLOAD_PATH = os.getenv("UPLOAD_PATH", "./data/uploads")   # local file storage for dev
S3_BUCKET = os.getenv("S3_BUCKET", "")                     # empty = local mode, set for prod

# Pre-signed URL
PRESIGNED_URL_EXPIRY = 900  # 15 minutes — enough to upload, short enough for security

# Worker Settings
WORKER_POLL_WAIT_SECONDS = int(os.getenv("WORKER_POLL_WAIT_SECONDS", "20"))
WORKER_MAX_MESSAGES = int(os.getenv("WORKER_MAX_MESSAGES", "1"))
