# 新規作成（importしない）。理由: LambdaのPackageTypeはZip→Imageへその場変更できないため、
# 今のZip版(cest-backend)は先にCloudShellで手動削除してから、ここでコンテナ版として作り直す。
# 関数名を同じ "cest-backend" にすることで、Lambdaの ARN が変わらず、
# API Gateway側の統合設定を一切変更せずに済む。

resource "aws_ecr_repository" "cest_api" {
  name                 = "cest-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_iam_role" "lambda_exec" {
  name = "cest-backend-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# 最小権限: CloudWatch Logsへの書き込みのみ（AWS管理の基本ポリシー）
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "cest_api" {
  function_name = "cest-backend"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.cest_api.repository_url}:${var.image_tag}"
  role          = aws_iam_role.lambda_exec.arn
  memory_size   = 512
  timeout       = 30

  # ECRに最低1枚イメージが無いと関数を作成できないため、
  # Step4のブートストラップでCloudShellから最初の1枚を先にpushしておく必要がある。
}

# API GatewayがこのLambdaを呼び出すことを許可する（見落としがちだが必須）
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cest_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.cest.execution_arn}/*/*"
}
