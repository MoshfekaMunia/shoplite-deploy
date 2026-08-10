variable "namespace" {
  description = "Namespace to create for the application."
  type        = string
}

variable "kubeconfig_path" {
  description = "Path to the kubeconfig used to reach the cluster."
  type        = string
}
