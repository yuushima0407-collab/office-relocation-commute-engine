variable "image_tag" {
  description = "LambdaコンテナイメージのECRタグ。GitHub Actionsがコミットのshort SHAを渡す。ローカルでの初回applyでは 'bootstrap' を使う"
  type        = string
  default     = "bootstrap"
}

variable "github_repo" {
  description = "GitHub OIDCで信頼するリポジトリ（org/repo形式）"
  type        = string
  default     = "yuushima0407-collab/office-relocation-commute-engine"
}
