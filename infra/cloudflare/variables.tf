variable "cloudflare_api_token" {
  description = "Scoped token with zone ruleset permissions."
  type        = string
  sensitive   = true
}

variable "zone_id" {
  description = "Cloudflare zone identifier for the public application domain."
  type        = string
}

variable "app_hostname" {
  description = "Public hostname served by the Cloudflare Worker."
  type        = string
}

variable "requests_per_minute" {
  description = "Per-IP request ceiling at the edge."
  type        = number
  default     = 120
}

variable "mutations_per_minute" {
  description = "Per-IP POST, PUT, PATCH, and DELETE ceiling at the edge."
  type        = number
  default     = 20
}
