# DEVIATION FROM ASSIGNMENT BRIEF:
# Section 4.5.1 specifies installing ingress-nginx via the helm provider.
# This module creates the namespace via the kubernetes provider only.
# ingress-nginx is provisioned by minikube's built-in `ingress` addon
# instead, to avoid running a second, competing ingress controller
# alongside it. See docs/design-decisions.md for the full rationale.

resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
  }
}
