terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.16"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region = "ap-southeast-2"
}

resource "aws_security_group" "ssh_access" {
  name = "fastapi-ec2-sg"
  description = "adds appropriate ssh permission"
  ingress {
    cidr_blocks = ["0.0.0.0/0"]
    from_port = 22
    to_port = 22
    protocol = "tcp"
  }
  ingress {
    cidr_blocks = ["0.0.0.0/0"]
    from_port = 0
    to_port = 0
    protocol = "-1"
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "api-server" {
  ami           = "ami-0c71c4b6e6896eda5"
  instance_type = "t2.micro"
  tags = {
    Name = var.instance_name
  }
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }
  user_data = file("scripts/start_script.sh")
  security_groups = [aws_security_group.ssh_access.name]
  key_name = "KafkaKeyPair"
}