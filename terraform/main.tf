provider "kubernetes" {
  config_path = var.kubeconfig_path
}

module "cluster" {
  source = "./modules/cluster"

  cluster_name    = var.cluster_name
  kubeconfig_path = var.kubeconfig_path
}

module "platform" {
  source = "./modules/platform"

  namespace       = var.namespace
  kubeconfig_path = module.cluster.kubeconfig_path
}
