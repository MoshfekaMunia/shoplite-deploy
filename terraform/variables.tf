variable "cluster_name" {
  description = "Name of the local Kubernetes cluster."
  type        = string
  default     = "minikube"
}

variable "namespace" {
  description = "Kubernetes namespace the application is deployed into."
  type        = string
  default     = "shoplite"
}

variable "kubeconfig_path" {
  description = "Path to the kubeconfig file used to reach the cluster."
  type        = string
  default     = "~/.kube/config"
}
