output "cluster_name" {
  description = "Name of the cluster in use."
  value       = module.cluster.cluster_name
}

output "kubeconfig_path" {
  description = "Path to the kubeconfig used to reach the cluster."
  value       = module.cluster.kubeconfig_path
}

output "namespace" {
  description = "Namespace created for the application."
  value       = module.platform.namespace
}

output "ingress_class" {
  description = "IngressClass installed by the platform module."
  value       = module.platform.ingress_class
}
