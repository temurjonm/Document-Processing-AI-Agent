# Document Processing AI Agent

FastAPI-based document ingestion and retrieval app with hybrid search, agent mode, and an optional AWS-backed async pipeline.

## Features

- PDF, DOCX, PNG, and JPEG upload support
- Hybrid retrieval with Chroma + BM25
- Search and agent query modes
- Local development mode with filesystem uploads
- Full AWS mode with S3 + SQS + DynamoDB + worker
- Terraform deployment for AWS infrastructure

## Local Setup

1. Create a virtual environment and install dependencies.
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy the example environment file and add your OpenAI key.
```bash
cp .env.example .env
```

3. For local mode, keep these values blank in `.env`:
```env
S3_BUCKET=
DOC_STATUS_TABLE=
INGESTION_QUEUE_URL=
```

4. Start the API.
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

5. Verify health.
```bash
curl http://localhost:8000/health
```

## Terraform Deployment

The Terraform stack lives in [`infra/terraform`](infra/terraform).

1. Copy the example vars file.
```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

2. Set your real `allowed_ssh_cidr` in `infra/terraform/terraform.tfvars`.

3. Pick a deployment mode:
- `test`: EC2-only, local upload mode
- `full`: EC2 + S3 + SQS + DynamoDB + worker

4. Apply the stack.
```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform apply
```

## Security Notes

- Do not commit `.env`, Terraform state, or runtime data.
- Use AWS profiles, roles, or IAM Identity Center instead of putting long-lived AWS keys in `.env`.
- Rotate any credential that was ever copied into this repo or terminal history.
