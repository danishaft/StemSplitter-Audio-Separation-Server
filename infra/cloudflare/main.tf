resource "cloudflare_ruleset" "custom_firewall" {
  zone_id     = var.zone_id
  name        = "StemSplitter custom firewall"
  description = "Reject methods and paths outside the public application contract."
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules = [
    {
      action      = "block"
      description = "Block methods outside the public HTTP contract"
      expression  = "(http.host eq \"${var.app_hostname}\" and not http.request.method in {\"GET\" \"HEAD\" \"OPTIONS\" \"POST\" \"PUT\" \"PATCH\" \"DELETE\"})"
      ref         = "block_unexpected_methods"
    },
    {
      action      = "block"
      description = "Block common secret and repository probes"
      expression  = "(http.host eq \"${var.app_hostname}\" and http.request.uri.path matches \"(?i)^/(\\\\.env|\\\\.git|wp-admin|phpmyadmin)\")"
      ref         = "block_secret_probes"
    }
  ]
}

resource "cloudflare_ruleset" "rate_limits" {
  zone_id     = var.zone_id
  name        = "StemSplitter rate limits"
  description = "Bound abusive traffic before requests reach the control plane."
  kind        = "zone"
  phase       = "http_ratelimit"

  rules = [
    {
      action      = "block"
      description = "Global per-IP application rate limit"
      expression  = "(http.host eq \"${var.app_hostname}\")"
      ref         = "global_per_ip"
      ratelimit = {
        characteristics     = ["cf.colo.id", "ip.src"]
        mitigation_timeout  = 60
        period              = 60
        requests_per_period = var.requests_per_minute
      }
    },
    {
      action      = "block"
      description = "Mutation per-IP application rate limit"
      expression  = "(http.host eq \"${var.app_hostname}\" and starts_with(http.request.uri.path, \"/api/\"))"
      ref         = "mutations_per_ip"
      ratelimit = {
        characteristics     = ["cf.colo.id", "ip.src"]
        counting_expression = "(http.request.method in {\"POST\" \"PUT\" \"PATCH\" \"DELETE\"})"
        mitigation_timeout  = 60
        period              = 60
        requests_per_period = var.mutations_per_minute
      }
    }
  ]
}
