variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-2"
}

variable "instance_name" {
  description = "Name tag and container name for the deployed app."
  type        = string
  default     = "doc-processing-agent"
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 20
}

variable "app_port" {
  description = "Public port exposed by the app."
  type        = number
  default     = 8000
}

variable "deployment_mode" {
  description = "Deployment profile: test uses EC2-only local upload mode, full provisions S3/SQS/DynamoDB and the worker."
  type        = string
  default     = "test"

  validation {
    condition     = contains(["test", "full"], var.deployment_mode)
    error_message = "deployment_mode must be either \"test\" or \"full\"."
  }
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the instance."
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_ssh_cidr, 0)) && var.allowed_ssh_cidr != "203.0.113.10/32"
    error_message = "allowed_ssh_cidr must be a valid CIDR and cannot use the example value 203.0.113.10/32. Set it to your real public IP, typically as x.x.x.x/32."
  }
}

variable "ssh_public_key_path" {
  description = "Path to the local SSH public key Terraform should import into EC2."
  type        = string
  default     = "~/.ssh/doc-agent-rsa.pub"
}

variable "ssh_private_key_path" {
  description = "Path to the local SSH private key Terraform should use for provisioners."
  type        = string
  default     = "~/.ssh/doc-agent-rsa"
}

variable "key_pair_name" {
  description = "Name of the EC2 key pair resource Terraform will manage."
  type        = string
  default     = "doc-agent-terraform"
}

variable "documents_bucket_name" {
  description = "Optional override for the S3 bucket that stores uploaded documents."
  type        = string
  default     = null
}

variable "documents_table_name" {
  description = "Optional override for the DynamoDB table that stores document status."
  type        = string
  default     = null
}

variable "ingestion_queue_name" {
  description = "Optional override for the main SQS ingestion queue name."
  type        = string
  default     = null
}

variable "ingestion_dlq_name" {
  description = "Optional override for the SQS dead-letter queue name."
  type        = string
  default     = null
}

variable "s3_event_prefix" {
  description = "S3 key prefix that should trigger ingestion events."
  type        = string
  default     = "documents/"
}

variable "force_destroy_documents_bucket" {
  description = "Whether Terraform should delete the S3 bucket even when it contains uploaded files."
  type        = bool
  default     = true
}

variable "existing_instance_profile_name" {
  description = "Optional existing IAM instance profile name to use instead of creating one in Terraform."
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Optional subnet override. Defaults to the first default subnet in the default VPC."
  type        = string
  default     = null
}

variable "local_env_file" {
  description = "Optional path to a local .env file that contains OPENAI_API_KEY."
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags to apply to AWS resources."
  type        = map(string)
  default     = {}
}
