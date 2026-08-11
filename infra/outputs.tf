output "api_gateway_endpoint" {
  value = aws_apigatewayv2_api.cest.api_endpoint
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.frontend.domain_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.cest_api.repository_url
}

output "github_actions_role_arn" {
  value       = aws_iam_role.github_actions.arn
  description = "これをGitHub SecretsのAWS_ROLE_ARNに登録する"
}
