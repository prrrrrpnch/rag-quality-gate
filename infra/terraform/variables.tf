variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "ap-south-1"
}

variable "name_prefix" {
  description = "Prefix for resource names (bucket names must be globally unique)."
  type        = string
  default     = "rqg"
}

variable "log_retention_days" {
  description = "Delete interaction logs after this many days."
  type        = number
  default     = 365
}

variable "results_retention_days" {
  description = "Delete Athena query results after this many days."
  type        = number
  default     = 7
}

variable "bytes_scanned_cutoff_per_query" {
  description = "Hard cap on bytes one Athena query may scan (cost control). 1 GiB default."
  type        = number
  default     = 1073741824
}
