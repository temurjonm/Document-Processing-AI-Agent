locals {
  normalized_name = trim(replace(lower(var.instance_name), "/[^a-z0-9-]/", "-"), "-")
  project_root    = abspath("${path.module}/../..")
  deployment_root = "/opt/doc-agent"
  env_file_path   = pathexpand(var.local_env_file != null ? var.local_env_file : "${local.project_root}/.env")
  ssh_public_key  = pathexpand(var.ssh_public_key_path)
  ssh_private_key = pathexpand(var.ssh_private_key_path)
  full_mode       = var.deployment_mode == "full"
  documents_bucket_name = coalesce(
    var.documents_bucket_name,
    "${local.normalized_name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}-docs",
  )
  documents_table_name = coalesce(var.documents_table_name, "${local.normalized_name}-documents")
  ingestion_queue_name = coalesce(var.ingestion_queue_name, "${local.normalized_name}-ingestion")
  ingestion_dlq_name   = coalesce(var.ingestion_dlq_name, "${local.normalized_name}-ingestion-dlq")
  documents_bucket_env = local.full_mode ? aws_s3_bucket.documents[0].bucket : ""
  documents_table_env  = local.full_mode ? aws_dynamodb_table.documents[0].name : ""
  ingestion_queue_env  = local.full_mode ? aws_sqs_queue.ingestion[0].id : ""
  worker_enabled       = local.full_mode
  instance_profile_name = local.full_mode ? (
    var.existing_instance_profile_name != null ? var.existing_instance_profile_name : aws_iam_instance_profile.doc_agent[0].name
  ) : null
  synced_files = sort(concat(
    [".dockerignore", "Dockerfile", "main.py", "requirements.txt"],
    tolist(fileset(local.project_root, "src/**"))
  ))
  app_source_hash = sha1(join("", [for relpath in local.synced_files : filesha1("${local.project_root}/${relpath}")]))
  env_source_hash = filesha1(local.env_file_path)
  selected_subnet = var.subnet_id != null ? var.subnet_id : sort(data.aws_subnets.default.ids)[0]
}
