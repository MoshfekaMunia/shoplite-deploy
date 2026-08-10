output "cluster_name" {
  description = "Name of the minikube cluster profile."
  value       = var.cluster_name
}

output "kubeconfig_path" {
  description = "Path to the kubeconfig this cluster is registered in."
  value       = var.kubeconfig_path
}
