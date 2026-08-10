output "namespace" {
  description = "Namespace created for the application."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "ingress_class" {
  description = "IngressClass provisioned by minikube's ingress addon (not by this module)."
  value       = "nginx"
}
