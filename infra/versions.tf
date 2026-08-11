terraform {
  required_version = ">= 1.10" # S3バックエンドのネイティブロック機能(use_lockfile)に必要

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # このstateバケットはTerraform管理外。Step1で手動作成する。
  backend "s3" {
    bucket       = "cest-terraform-state-yuki-shimada"
    key          = "cest/terraform.tfstate"
    region       = "ap-northeast-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = "ap-northeast-1"
}

# GitHub ActionsのOIDC用サムプリント取得に必要（us-east-1固定ではなく、GitHub側のエンドポイントを見る）
provider "tls" {}
