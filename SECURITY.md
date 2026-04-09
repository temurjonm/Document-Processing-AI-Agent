# Security Notes

## Before Publishing

- Do not commit `.env` or any file that contains API keys or secrets.
- Do not commit Terraform state, logs, or local runtime data.
- Do not publish uploaded documents, embeddings, or Chroma persistence files.
- Prefer AWS profiles, instance roles, or IAM Identity Center over long-lived AWS access keys.

## If A Secret Was Exposed

Rotate it immediately:

- OpenAI API keys
- AWS access keys
- any SSH private keys or certificates

Then remove the secret from your local files before pushing.
