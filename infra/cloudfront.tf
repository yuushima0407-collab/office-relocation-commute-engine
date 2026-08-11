# 既存OAC。terraform importで取り込む対象（Step3）。
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "cest-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# 既存ディストリビューション。terraform importで取り込む対象（Step3）。
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_All"
  http_version        = "http2"
  is_ipv6_enabled     = true

  # CloudFront作成時に無料バンドルされた基本保護（IPレピュテーションリスト等）。
  # 追加課金は発生しないことを確認済みなので維持する（詳細はaws-architecture.md参照）。
  web_acl_id = "arn:aws:wafv2:us-east-1:697629627446:global/webacl/CreatedByCloudFront-d22f1119/1e1e9db6-51fd-4b0b-89b6-033927a9a0a8"

  # 実際に今のディストリビューションが使ってるorigin_idの文字列をそのまま使う。
  # import後にplanの差分をゼロにするため、AWSが自動生成したIDを変えずに合わせている。
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "cest-frontend-yuki-shimada-2026.s3.ap-northeast-1.amazonaws.com-mp4wdkb9t27"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id       = "cest-frontend-yuki-shimada-2026.s3.ap-northeast-1.amazonaws.com-mp4wdkb9t27"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods          = ["GET", "HEAD"]
    compress                = true
    cache_policy_id         = "658327ea-f89d-4fab-a63d-7e88639e58f6" # AWS管理ポリシー: CachingOptimized
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1"
  }
}
