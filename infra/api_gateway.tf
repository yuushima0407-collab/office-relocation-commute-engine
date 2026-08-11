# 既存API。terraform importで取り込む対象（Step3）。
resource "aws_apigatewayv2_api" "cest" {
  name          = "cest-api"
  protocol_type = "HTTP"

  # 今のAPI Gatewayに実在する設定。消すとブラウザからのAPI呼び出しが壊れる恐れがあるため、
  # そのまま維持する（バックエンド側のCORSMiddlewareと二重にはなるが、削除するリスクを取らない）。
  cors_configuration {
    allow_credentials = false
    allow_headers      = ["*"]
    allow_methods      = ["*"]
    allow_origins      = ["*"]
    expose_headers     = []
    max_age            = 86400
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.cest.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.cest_api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.cest.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.cest.id
  name        = "$default"
  auto_deploy = true # 現状はfalseだが、Terraform管理下では変更が即反映される方が事故りにくいためtrueにする

  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 10
  }
}
