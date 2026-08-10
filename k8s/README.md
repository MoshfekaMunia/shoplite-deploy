# ShopLite — Kubernetes Deployment (minikube)

This document covers running ShopLite on Kubernetes locally via `minikube`,
as a follow-on to the Docker Compose setup described in the repository's
main `README.md`. For the full narrative of how this was built, including
every bug hit along the way, see
[`docs/kubernetes-deployment-process.md`](../docs/kubernetes-deployment-process.md).

> **Note on `minikube` vs `kind`:** the assignment brief specifies a `kind`
> cluster provisioned via Terraform's `tehcyx/kind` provider. This
> deployment uses `minikube` instead, since that was the tool already
> available in this environment. Cluster creation is therefore done via the
> `minikube` CLI rather than Terraform's `tehcyx/kind` provider; see
> `docs/design-decisions.md` for the full rationale.

## Prerequisites

- Docker Engine
- `kubectl`
- `minikube`
- `terraform` (for the `cluster`/`platform` modules)
- The four ShopLite service images build cleanly (see main `README.md` for
  the Compose-based smoke test)

## 1. Provision the cluster and namespace with Terraform

```bash
cd terraform
terraform init
terraform apply
```

This starts minikube (via the `cluster` module) and creates the `shoplite`
namespace (via the `platform` module). See `terraform/README.md`-level
comments in the module source for the `kind`/`helm` deviations.

## 2. Build and load the four service images

minikube (docker driver) uses its own Docker daemon, separate from the
host's. Images built normally with `docker build` are **not** visible
inside the cluster until explicitly loaded:

```bash
docker build -t shoplite/user-service:v1 ./services/user-service
docker build -t shoplite/catalog-service:v1 ./services/catalog-service
docker build -t shoplite/order-service:v1 ./services/order-service
docker build -t shoplite/notification-service:v1 ./services/notification-service

minikube image load shoplite/user-service:v1
minikube image load shoplite/catalog-service:v1
minikube image load shoplite/order-service:v1
minikube image load shoplite/notification-service:v1
```

Verify:

```bash
minikube image ls | grep shoplite
```

## 3. Apply the manifests

Order matters — config first, then data layer, then application services,
then Ingress:

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

kubectl apply -f k8s/data/user-db.yaml
kubectl apply -f k8s/data/order-db.yaml
kubectl apply -f k8s/data/catalog-db.yaml
kubectl apply -f k8s/data/notification-db.yaml
kubectl apply -f k8s/data/rabbitmq.yaml

kubectl wait --for=condition=Ready pod -l app=user-db -n shoplite --timeout=120s
kubectl wait --for=condition=Ready pod -l app=order-db -n shoplite --timeout=120s
kubectl wait --for=condition=Ready pod -l app=catalog-db -n shoplite --timeout=120s
kubectl wait --for=condition=Ready pod -l app=notification-db -n shoplite --timeout=120s
kubectl wait --for=condition=Ready pod -l app=rabbitmq -n shoplite --timeout=180s

kubectl apply -f k8s/services/user-service.yaml
kubectl apply -f k8s/services/catalog-service.yaml
kubectl apply -f k8s/services/order-service.yaml
kubectl apply -f k8s/services/notification-service.yaml

kubectl apply -f k8s/ingress.yaml
```

Note: the `shoplite` namespace itself is created by Terraform (step 1), not
`kubectl apply -f k8s/namespace.yaml` — its lifecycle is owned by Terraform
state.

## 4. Point your machine at the Ingress

```bash
echo "$(minikube ip) shoplite.local" | sudo tee -a /etc/hosts
```

Using `minikube ip` rather than `127.0.0.1` matters here: minikube's
`docker` driver runs the cluster inside its own container with its own IP,
unlike `kind`, which typically maps the ingress controller directly onto
`localhost`.

## 5. Verify

```bash
kubectl get pods -n shoplite
```

Expect 13 pods, all `Running`: 4 databases, RabbitMQ, and 4 application
services at 2 replicas each.

```bash
curl http://shoplite.local/api/users/1
curl http://shoplite.local/api/products
curl http://shoplite.local/api/orders/1
curl http://shoplite.local/api/notifications/1
```

Or open `http://shoplite.local` directly in a browser for the full UI.

### Full functional demo

```bash
curl -X POST http://shoplite.local/api/users \
  -H "Content-Type: application/json" \
  -d '{"name":"Amina Rahman","email":"amina@example.com"}'

curl -X POST http://shoplite.local/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Mechanical keyboard","price":29.99,"attributes":{"layout":"US"}}'

# copy the "id" from the product response into the next command
curl -X POST http://shoplite.local/api/orders \
  -H "Content-Type: application/json" \
  -d '{"userId":1,"productId":"<paste product id>","quantity":2}'

curl http://shoplite.local/api/notifications/1
```

## Demonstration 1 — Manual scaling (S10)

```bash
kubectl scale deployment order-service --replicas=5 -n shoplite
kubectl get pods -n shoplite -l app=order-service -w
```

Captured output:
deployment.apps/order-service scaled
NAME READY STATUS RESTARTS AGE
order-service-59b485fb6-c6bzj 0/1 ContainerCreating 0 1s
order-service-59b485fb6-dm7xk 0/1 ContainerCreating 0 1s
order-service-59b485fb6-lmvr4 1/1 Running 0 10m
order-service-59b485fb6-mjpb9 0/1 ContainerCreating 0 1s
order-service-59b485fb6-t6rph 1/1 Running 0 10m
order-service-59b485fb6-dm7xk 0/1 Running 0 1s
order-service-59b485fb6-mjpb9 0/1 Running 0 2s
order-service-59b485fb6-c6bzj 0/1 Running 0 2s
order-service-59b485fb6-mjpb9 1/1 Running 0 8s
order-service-59b485fb6-dm7xk 1/1 Running 0 8s
order-service-59b485fb6-c6bzj 1/1 Running 0 9s

**What happens to traffic while new pods start:** the 2 pre-existing
`order-service` pods (`lmvr4`, `t6rph`) keep serving requests unaffected
throughout. The 3 new pods (`c6bzj`, `dm7xk`, `mjpb9`) start in `0/1` —
container running, but not yet marked ready. Because the Service's
`selector` only routes traffic to pods that pass their `readinessProbe`
(`GET /readyz`), Kubernetes never sends a real user request to a pod that
hasn't confirmed it can reach its dependencies. Only once each new pod
flips to `1/1` does it start receiving traffic. This is exactly why the
readiness probe exists separately from the liveness probe: it gates
traffic, not process lifecycle.

## Demonstration 2 — Resilience: database pod failure (S11)

```bash
kubectl get pods -n shoplite -l app=order-db
kubectl scale deployment order-db --replicas=0 -n shoplite
sleep 20
kubectl get pods -n shoplite -l app=order-service
kubectl scale deployment order-db --replicas=1 -n shoplite
kubectl get pods -n shoplite -l app=order-service -w
```

Captured output:
NAME READY STATUS RESTARTS AGE
order-db-7b96844c94-r5klv 1/1 Running 0 2m38s
deployment.apps/order-db scaled

NAME READY STATUS RESTARTS AGE
order-service-59b485fb6-c6bzj 0/1 Running 0 6m23s
order-service-59b485fb6-dm7xk 0/1 Running 0 6m23s
order-service-59b485fb6-lmvr4 0/1 Running 0 16m
order-service-59b485fb6-mjpb9 0/1 Running 0 6m23s
order-service-59b485fb6-t6rph 0/1 Running 0 16m
deployment.apps/order-db scaled

order-service-59b485fb6-t6rph 1/1 Running 0 16m
order-service-59b485fb6-lmvr4 1/1 Running 0 16m
order-service-59b485fb6-mjpb9 1/1 Running 0 6m28s
order-service-59b485fb6-dm7xk 1/1 Running 0 6m28s
order-service-59b485fb6-c6bzj 1/1 Running 0 6m29s

**What this demonstrates:** with `order-db` scaled to zero, all five
`order-service` pods flip to `READY: 0/1` — the readiness probe (`GET
/readyz`, which pings the database) correctly detects the dependency is
gone and Kubernetes stops routing traffic to them. Critically,
`RESTARTS` stays at `0` and `STATUS` stays `Running` throughout — the
liveness probe (`GET /healthz`, which checks nothing but the process
itself) never fails, so Kubernetes never kills or restarts the
containers. Once `order-db` is scaled back to 1 and becomes ready again,
all five `order-service` pods automatically return to `1/1 Running` with
no manual intervention. This is the exact behavior section 4.6.2 of the
brief describes: separating liveness from readiness prevents a database
hiccup from turning into a full service outage via unnecessary restarts.

## After a VM or host reboot

minikube runs as a Docker container and does not auto-start with the OS.
Cluster state (all deployments, PVC data) is preserved across a normal
restart, so you only need to bring it back up — no need to reapply
manifests:

```bash
minikube start
kubectl get pods -n shoplite
kubectl get ingress -n shoplite
```

If `kubectl` reports `no route to host` immediately after a restart, this
is almost always just minikube not having started yet — run `minikube
start` first.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `CrashLoopBackOff`, logs show a literal `$(VAR_NAME)` in a connection string | Env var referencing another var declared **later** in the same `env:` list | Reorder so source vars (user/password/name) come before the composed URL that references them |
| Pod stuck `Pending`, `describe` shows `Insufficient cpu` | Not enough CPU allocated to the minikube VM for all requested pods | Increase VM/minikube `--cpus`, or lower `resources.requests.cpu` per container |
| `ImagePullBackOff` | Image wasn't loaded into minikube's Docker daemon, or `imagePullPolicy` isn't `IfNotPresent` | `minikube image load <image>` and confirm `imagePullPolicy: IfNotPresent` in the Deployment |
| Ingress returns generic `{"detail":"Not Found"}` on every route | A `rewrite-target` regex stripping more of the path than intended | Confirm the app's actual expected path (`kubectl port-forward` + curl directly to the Service) before adding any rewrite; often no rewrite is needed |
| `no route to host` after VM/host reboot | minikube's container isn't running | `minikube start` |
| `minikube start` warns about low disk space | VM's virtual disk is nearly full | Resize the `.vdi` via `VBoxManage modifymedium --resize`, then `growpart` + `resize2fs` inside the VM |
| `terraform apply` fails with "namespace already exists" | Namespace was created manually via `kubectl` before Terraform managed it | `terraform import module.platform.kubernetes_namespace.app <namespace>` |

