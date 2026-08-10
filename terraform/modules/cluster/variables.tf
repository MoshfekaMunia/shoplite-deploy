variable "cluster_name" {
  description = "Name minikube will use for the cluster profile."
  type        = string
}

variable "kubeconfig_path" {
  description = "Path to the kubeconfig minikube writes its context into."
  type        = string
}

variable "cpus" {
  description = "CPUs to allocate to the minikube VM."
  type        = number
  default     = 4
}

variable "memory_mb" {
  description = "Memory (MB) to allocate to the minikube VM."
  type        = number
  default     = 3600
}
