variable "region" {
  type = string
}

variable "oci_profile" {
  type    = string
  default = "DEFAULT"
}

variable "tenancy_ocid" {
  type = string
}

variable "compartment_ocid" {
  type = string
}

variable "admin_cidr" {
  description = "Your IP in CIDR form. Only this range can reach ssh and http(s)."
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "admin_cidr must be a valid CIDR and not the whole internet."
  }
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

variable "ocpus" {
  type    = number
  default = 4
}

variable "memory_gb" {
  type    = number
  default = 12
}

variable "boot_volume_gb" {
  type    = number
  default = 100
}

variable "availability_domain_index" {
  description = "A1 capacity is often exhausted in one AD; bump this if launch fails."
  type        = number
  default     = 0
}

variable "k3s_version" {
  type    = string
  default = "v1.36.5+k3s1"
}
