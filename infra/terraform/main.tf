data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
}

resource "aws_s3_bucket" "documents" {
  count         = local.full_mode ? 1 : 0
  bucket        = local.documents_bucket_name
  force_destroy = var.force_destroy_documents_bucket

  tags = merge(var.tags, {
    Name = local.documents_bucket_name
  })
}

resource "aws_s3_bucket_public_access_block" "documents" {
  count  = local.full_mode ? 1 : 0
  bucket = aws_s3_bucket.documents[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  count  = local.full_mode ? 1 : 0
  bucket = aws_s3_bucket.documents[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "documents" {
  count        = local.full_mode ? 1 : 0
  name         = local.documents_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_id"

  attribute {
    name = "doc_id"
    type = "S"
  }

  tags = merge(var.tags, {
    Name = local.documents_table_name
  })
}

resource "aws_sqs_queue" "ingestion_dlq" {
  count                     = local.full_mode ? 1 : 0
  name                      = local.ingestion_dlq_name
  message_retention_seconds = 1209600

  tags = merge(var.tags, {
    Name = local.ingestion_dlq_name
  })
}

resource "aws_sqs_queue" "ingestion" {
  count                      = local.full_mode ? 1 : 0
  name                       = local.ingestion_queue_name
  visibility_timeout_seconds = 300
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingestion_dlq[0].arn
    maxReceiveCount     = 5
  })

  tags = merge(var.tags, {
    Name = local.ingestion_queue_name
  })
}

data "aws_iam_policy_document" "ingestion_queue" {
  count = local.full_mode ? 1 : 0

  statement {
    sid     = "AllowS3EventNotifications"
    effect  = "Allow"
    actions = ["sqs:SendMessage"]
    resources = [
      aws_sqs_queue.ingestion[0].arn,
    ]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.documents[0].arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "ingestion" {
  count     = local.full_mode ? 1 : 0
  queue_url = aws_sqs_queue.ingestion[0].id
  policy    = data.aws_iam_policy_document.ingestion_queue[0].json
}

resource "aws_s3_bucket_notification" "documents" {
  count  = local.full_mode ? 1 : 0
  bucket = aws_s3_bucket.documents[0].id

  queue {
    queue_arn     = aws_sqs_queue.ingestion[0].arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = var.s3_event_prefix
  }

  depends_on = [aws_sqs_queue_policy.ingestion]
}

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "doc_agent" {
  count              = local.full_mode && var.existing_instance_profile_name == null ? 1 : 0
  name               = "${local.normalized_name}-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = merge(var.tags, {
    Name = "${local.normalized_name}-role"
  })
}

data "aws_iam_policy_document" "doc_agent" {
  count = local.full_mode && var.existing_instance_profile_name == null ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:DeleteItem",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [aws_dynamodb_table.documents[0].arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.documents[0].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.documents[0].arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage",
    ]
    resources = [aws_sqs_queue.ingestion[0].arn]
  }
}

resource "aws_iam_role_policy" "doc_agent" {
  count  = local.full_mode && var.existing_instance_profile_name == null ? 1 : 0
  name   = "${local.normalized_name}-access"
  role   = aws_iam_role.doc_agent[0].id
  policy = data.aws_iam_policy_document.doc_agent[0].json
}

resource "aws_iam_instance_profile" "doc_agent" {
  count = local.full_mode && var.existing_instance_profile_name == null ? 1 : 0
  name  = "${local.normalized_name}-profile"
  role  = aws_iam_role.doc_agent[0].name

  tags = merge(var.tags, {
    Name = "${local.normalized_name}-profile"
  })
}

resource "aws_key_pair" "doc_agent" {
  key_name   = var.key_pair_name
  public_key = file(local.ssh_public_key)

  tags = merge(var.tags, {
    Name = var.key_pair_name
  })
}

resource "aws_security_group" "doc_agent" {
  name        = "${var.instance_name}-sg"
  description = "SSH and app access for ${var.instance_name}"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "App"
    from_port   = var.app_port
    to_port     = var.app_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.instance_name}-sg"
  })
}

resource "aws_instance" "doc_agent" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  iam_instance_profile        = local.instance_profile_name
  key_name                    = aws_key_pair.doc_agent.key_name
  subnet_id                   = local.selected_subnet
  vpc_security_group_ids      = [aws_security_group.doc_agent.id]
  associate_public_ip_address = false
  user_data                   = templatefile("${path.module}/user_data.sh.tftpl", { deployment_root = local.deployment_root })
  user_data_replace_on_change = true

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = merge(var.tags, {
    Name = var.instance_name
  })
}

resource "aws_eip" "doc_agent" {
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.instance_name}-ip"
  })
}

resource "aws_eip_association" "doc_agent" {
  allocation_id = aws_eip.doc_agent.id
  instance_id   = aws_instance.doc_agent.id
}

resource "terraform_data" "app_deploy" {
  depends_on = [aws_eip_association.doc_agent]

  triggers_replace = [
    aws_instance.doc_agent.id,
    local.app_source_hash,
    local.env_source_hash,
    tostring(var.app_port),
    var.deployment_mode,
    local.documents_bucket_env,
    local.documents_table_env,
    local.ingestion_queue_env,
  ]

  connection {
    type        = "ssh"
    host        = aws_eip.doc_agent.public_ip
    user        = "ec2-user"
    private_key = file(local.ssh_private_key)
  }

  provisioner "remote-exec" {
    inline = [
      "mkdir -p /tmp/doc-agent"
    ]
  }

  provisioner "file" {
    source      = "${local.project_root}/.dockerignore"
    destination = "/tmp/doc-agent/.dockerignore"
  }

  provisioner "file" {
    source      = "${local.project_root}/Dockerfile"
    destination = "/tmp/doc-agent/Dockerfile"
  }

  provisioner "file" {
    source      = "${local.project_root}/main.py"
    destination = "/tmp/doc-agent/main.py"
  }

  provisioner "file" {
    source      = "${local.project_root}/requirements.txt"
    destination = "/tmp/doc-agent/requirements.txt"
  }

  provisioner "file" {
    source      = "${local.project_root}/src"
    destination = "/tmp/doc-agent/"
  }

  provisioner "file" {
    source      = local.env_file_path
    destination = "/tmp/doc-agent/local.env"
  }

  provisioner "remote-exec" {
    inline = [<<-EOT
      set -euxo pipefail
      for i in $(seq 1 120); do
        if [ -f ${local.deployment_root}/.bootstrap-complete ] && command -v docker >/dev/null 2>&1 && sudo systemctl is-active --quiet docker; then
          break
        fi
        sleep 3
      done

      command -v docker >/dev/null 2>&1
      sudo systemctl is-active --quiet docker

      sudo install -d -o ec2-user -g ec2-user ${local.deployment_root}
      sudo install -d -o ec2-user -g ec2-user ${local.deployment_root}/app
      sudo install -d -o ec2-user -g ec2-user ${local.deployment_root}/data
      sudo install -d -o ec2-user -g ec2-user ${local.deployment_root}/data/uploads
      sudo install -d -o ec2-user -g ec2-user ${local.deployment_root}/data/chroma

      sudo rsync -a --delete --exclude 'local.env' /tmp/doc-agent/ ${local.deployment_root}/app/

      OPENAI_LINE="$(grep '^OPENAI_API_KEY=' /tmp/doc-agent/local.env | tail -n1 || true)"
      if [ -z "$OPENAI_LINE" ]; then
        echo "OPENAI_API_KEY is missing from /tmp/doc-agent/local.env" >&2
        exit 1
      fi

      sudo bash -c "cat > ${local.deployment_root}/.env <<'EOF'
$OPENAI_LINE
AWS_REGION=${var.aws_region}
CHROMA_PATH=/app/data/chroma
UPLOAD_PATH=/app/data/uploads
S3_BUCKET=${local.documents_bucket_env}
DOC_STATUS_TABLE=${local.documents_table_env}
INGESTION_QUEUE_URL=${local.ingestion_queue_env}
EOF"
      sudo chown ec2-user:ec2-user ${local.deployment_root}/.env
      sudo chmod 600 ${local.deployment_root}/.env

      cd ${local.deployment_root}/app
      sudo docker build -t ${var.instance_name}:latest .

      if sudo docker ps -a --format '{{.Names}}' | grep -qx '${var.instance_name}-api'; then
        sudo docker rm -f ${var.instance_name}-api
      fi

      if sudo docker ps -a --format '{{.Names}}' | grep -qx '${var.instance_name}-worker'; then
        sudo docker rm -f ${var.instance_name}-worker
      fi

      sudo docker run -d \
        --name ${var.instance_name}-api \
        --restart unless-stopped \
        -p ${var.app_port}:8000 \
        --env-file ${local.deployment_root}/.env \
        -v ${local.deployment_root}/data:/app/data \
        ${var.instance_name}:latest

      if [ -n "${local.ingestion_queue_env}" ]; then
        sudo docker run -d \
          --name ${var.instance_name}-worker \
          --restart unless-stopped \
          --env-file ${local.deployment_root}/.env \
          -v ${local.deployment_root}/data:/app/data \
          ${var.instance_name}:latest \
          python -m src.ingestion.sqs_worker
      fi

      for i in $(seq 1 30); do
        if curl -sf http://localhost:${var.app_port}/health >/dev/null; then
          exit 0
        fi
        sleep 2
      done

      sudo docker logs ${var.instance_name}-api || true
      sudo docker logs ${var.instance_name}-worker || true
      exit 1
    EOT
    ]
  }
}
