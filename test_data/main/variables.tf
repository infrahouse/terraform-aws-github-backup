variable "subnets" {
  type = list(string)
}

variable "region" {
  type = string
}

variable "role_arn" {
  type    = string
  default = null
}

variable "github_app_id" {
  type = string
}

variable "github_app_installation_id" {
  type = string
}
