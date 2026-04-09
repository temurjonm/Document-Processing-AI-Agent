# Terraform Deployment

This Terraform stack supports two deployment profiles from the same repo.

## What It Manages

- EC2 instance in the default VPC
- Security group for SSH and the app port
- EC2 key pair imported from your local SSH public key
- Elastic IP so the app endpoint stays stable
- Docker on the host
- App sync from this repo over SSH
- API container build and restart on each `terraform apply` when app files change
- Optional S3, SQS, DynamoDB, IAM role, and worker container in `full` mode

## Modes

`test` mode:

- EC2, Elastic IP, security group, key pair, Docker, and the API container
- Local upload mode via `/api/documents/{doc_id}/upload-local`
- In-memory document status and local uploads on the EC2 volume
- Works with limited-permission test AWS accounts

`full` mode:

- Adds S3 upload bucket
- Adds SQS + DLQ
- Adds DynamoDB document status store
- Adds IAM role / instance profile
- Runs the worker container

The application code is the same in both modes. `test` mode just uses the existing local fallback path.

## Prerequisites

- Terraform `>= 1.6`
- AWS CLI already configured for the target account
- A local SSH key pair available on this machine
- A local `.env` file at the repo root containing `OPENAI_API_KEY=...`

Defaults expect:

- public key: `~/.ssh/doc-agent-rsa.pub`
- private key: `~/.ssh/doc-agent-rsa`
- env file: repo root `.env`

Use `deployment_mode = "test"` if your IAM user cannot create DynamoDB, SQS, or IAM resources. Use `deployment_mode = "full"` only when those permissions exist.

## First Apply

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set at least:

- `allowed_ssh_cidr` to your real public IP in CIDR form
- `deployment_mode = "test"` for restricted test accounts
- optionally `existing_instance_profile_name` only for `full` mode if IAM role creation is blocked but a profile already exists

Then run:

```bash
terraform init
terraform apply
```

## After Apply

Get the app endpoint:

```bash
terraform output health_url
```

In `full` mode, these outputs are also populated:

```bash
terraform output documents_bucket
terraform output documents_table
terraform output ingestion_queue_url
```

SSH in:

```bash
terraform output ssh_command
```

## Updates

Run `terraform apply` again after code changes. Terraform hashes:

- `main.py`
- `requirements.txt`
- `Dockerfile`
- `.dockerignore`
- everything under `src/`
- the local `.env` file

When those inputs change, Terraform re-syncs the app, rebuilds the image, and restarts the deployed containers.

## Destroy

```bash
terraform destroy
```

In `full` mode, the S3 bucket is configured with `force_destroy = true`, so destroying the stack also deletes uploaded documents.

## Notes

- The OpenAI key is read from your local `.env` during provisioning and written onto the EC2 host at `/opt/doc-agent/.env`.
- The key is not stored as a Terraform variable in this setup.
- App data persists on the EC2 root volume under `/opt/doc-agent/data`.
- The worker runs only in `full` mode as `python -m src.ingestion.sqs_worker` in a second container from the same image.
