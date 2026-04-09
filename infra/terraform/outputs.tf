output "instance_id" {
  description = "ID of the EC2 instance running the app."
  value       = aws_instance.doc_agent.id
}

output "public_ip" {
  description = "Elastic IP attached to the instance."
  value       = aws_eip.doc_agent.public_ip
}

output "public_dns" {
  description = "Public DNS name attached to the instance."
  value       = aws_instance.doc_agent.public_dns
}

output "health_url" {
  description = "Health endpoint for the deployed app."
  value       = "http://${aws_eip.doc_agent.public_ip}:${var.app_port}/health"
}

output "documents_bucket" {
  description = "S3 bucket that stores uploaded documents."
  value       = local.full_mode ? aws_s3_bucket.documents[0].bucket : null
}

output "documents_table" {
  description = "DynamoDB table that stores document status and metadata."
  value       = local.full_mode ? aws_dynamodb_table.documents[0].name : null
}

output "ingestion_queue_url" {
  description = "SQS queue URL used by the ingestion worker."
  value       = local.full_mode ? aws_sqs_queue.ingestion[0].id : null
}

output "ssh_command" {
  description = "SSH command for direct access to the instance."
  value       = "ssh -i ${local.ssh_private_key} ec2-user@${aws_eip.doc_agent.public_ip}"
}
