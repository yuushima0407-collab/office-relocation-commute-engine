# 既存バケット。terraform importで取り込む対象（Step3）。
resource "aws_s3_bucket" "frontend" {
  bucket = "cest-frontend-yuki-shimada-2026"
}

# OACでCloudFront経由のみに絞ってるので、パブリックアクセスは全面ブロックでよい
# （バケットポリシーのPrincipalがcloudfront.amazonaws.comというAWSサービス限定のため、
#  「パブリックポリシーのブロック」には抵触しない）
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2008-10-17"
    Id      = "PolicyForCloudFrontPrivateContent"
    Statement = [{
      Sid       = "AllowCloudFrontServicePrincipal"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
        }
      }
    }]
  })
}
