# GitHub ActionsがAWSを操作するための入り口。長期のアクセスキーを持たせず、
# 実行のたびにAWSが短命な一時クレデンシャルを発行する仕組み(OIDC)。

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "github_actions" {
  name = "cest-github-actions-deploy"

  # mainブランチへのpushから起動したワークフローだけが、このロールを名乗れる
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect  = "Allow"
      Action  = "sts:AssumeRoleWithWebIdentity"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions" {
  name = "cest-deploy-permissions"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*" # このアクションはリソースレベル権限を取れない仕様
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories", # terraform apply -target=aws_lambda_function 実行時、依存先のECRリポジトリを参照するのに必要
        ]
        Resource = aws_ecr_repository.cest_api.arn
      },
      {
        Sid    = "S3Frontend"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject",
        ]
        Resource = [
          aws_s3_bucket.frontend.arn,
          "${aws_s3_bucket.frontend.arn}/*",
        ]
      },
      {
        Sid      = "CloudFrontInvalidate"
        Effect   = "Allow"
        Action   = ["cloudfront:CreateInvalidation"]
        Resource = aws_cloudfront_distribution.frontend.arn
      },
      {
        Sid    = "ManageLambda"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
        ]
        Resource = aws_lambda_function.cest_api.arn
      },
      {
        # CIは `terraform apply -target=aws_lambda_function.cest_api` のみ実行する運用にしている
        # （IAM/OIDCプロバイダ自体はCIに触らせない）。その際、Lambdaの実行ロール参照(role属性)を
        # 解決するために、依存先であるこのロールの読み取り権限だけが必要になる。
        Sid      = "ReadLambdaExecRole"
        Effect   = "Allow"
        Action   = ["iam:GetRole"]
        Resource = aws_iam_role.lambda_exec.arn
      },
      {
        Sid      = "ManageApiGateway"
        Effect   = "Allow"
        Action   = ["apigateway:*"]
        Resource = "arn:aws:apigateway:ap-northeast-1::/apis/${aws_apigatewayv2_api.cest.id}*"
      },
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::cest-terraform-state-yuki-shimada",
          "arn:aws:s3:::cest-terraform-state-yuki-shimada/*",
        ]
      },
    ]
  })
}
