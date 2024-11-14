variable "ami" {
  description = "Image for EC2 instances"
  type        = string
  default     = null
}

variable "app_key_secret" {
  description = "secret name where the GitHub PEM is stored."
  type        = string
}
variable "asg_min_size" {
  description = "Minimum number of instances in ASG"
  type        = number
  default     = 1
}

variable "asg_max_size" {
  description = "Maximum number of instances in ASG"
  type        = number
  default     = 1
}

variable "asg_min_healthy_percentage" {
  description = "Specifies the lower limit on the number of instances that must be in the InService state with a healthy status during an instance replacement activity."
  type        = number
  default     = 0
}

variable "asg_max_healthy_percentage" {
  description = "Specifies the upper limit on the number of instances that are in the InService or Pending state with a healthy status during an instance replacement activity."
  type        = number
  default     = 100

}

variable "subnets" {
  description = "Subnet ids where EC2 instances should be present"
  type        = list(string)
}

variable "environment" {
  description = "Name of environment"
  type        = string
  default     = "development"
}

variable "instance_role_name" {
  description = "If specified, the instance profile role will have this name. Otherwise, the role name will be generated."
  type        = string
  default     = "infrahouse-github-backup"
}

variable "instance_type" {
  description = "EC2 instances type"
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "SSH keypair name to be deployed in EC2 instances"
  type        = string
}

variable "max_instance_lifetime_days" {
  description = "The maximum amount of time, in _days_, that an instance can be in service, values must be either equal to 0 or between 7 and 365 days."
  type        = number
  default     = 30
}

variable "packages" {
  description = "List of packages to install when the instances bootstraps."
  type        = list(string)
  default     = []
}

variable "puppet_custom_facts" {
  description = "A map of custom puppet facts"
  type        = any
  default     = {}
}

variable "puppet_debug_logging" {
  description = "Enable debug logging if true."
  type        = bool
  default     = false
}

variable "puppet_environmentpath" {
  description = "A path for directory environments."
  default     = "{root_directory}/environments"
}

variable "puppet_hiera_config_path" {
  description = "Path to hiera configuration file."
  default     = "{root_directory}/environments/{environment}/hiera.yaml"
}

variable "puppet_manifest" {
  description = "Path to puppet manifest. By default ih-puppet will apply {root_directory}/environments/{environment}/manifests/site.pp."
  type        = string
  default     = null
}

variable "puppet_module_path" {
  description = "Path to common puppet modules."
  default     = "{root_directory}/environments/{environment}/modules:{root_directory}/modules"
}

variable "puppet_root_directory" {
  description = "Path where the puppet code is hosted."
  default     = "/opt/puppet-code"
}

variable "root_volume_size" {
  description = "Root volume size in EC2 instance in Gigabytes"
  type        = number
  default     = 30
}
variable "service_name" {
  description = "Descriptive name of a service that will use this VPC"
  type        = string
  default     = "infrahouse-github-backup"
}

variable "smtp_credentials_secret" {
  description = "AWS secret name with SMTP credentials. The secret must contain a JSON with user and password keys."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to instances in the autoscaling group."
  type        = map(string)
  default = {
    Name : "infrahouse-github-backup"
  }
}
