# DEVIATION FROM ASSIGNMENT BRIEF:
# The brief specifies a `kind` cluster provisioned via the `tehcyx/kind`
# Terraform provider. This environment has `minikube` installed instead of
# `kind`, so this module wraps the `minikube` CLI via null_resource +
# local-exec rather than using a dedicated Kubernetes-cluster provider.
# See docs/design-decisions.md for the full rationale.

resource "null_resource" "minikube_cluster" {
  triggers = {
    cluster_name = var.cluster_name
    cpus         = var.cpus
    memory_mb    = var.memory_mb
  }

  provisioner "local-exec" {
    command = "minikube start -p ${var.cluster_name} --cpus=${var.cpus} --memory=${var.memory_mb}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "minikube delete -p ${self.triggers.cluster_name}"
  }
}

resource "null_resource" "wait_for_node_ready" {
  depends_on = [null_resource.minikube_cluster]

  provisioner "local-exec" {
    command = "kubectl wait --for=condition=Ready node --all --timeout=120s"
  }
}
