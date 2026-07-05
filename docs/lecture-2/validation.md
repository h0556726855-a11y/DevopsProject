# Lecture 2 — Validation Checklist
## Kubernetes: Local Deployment with k3d

---

**Instructions:** Complete every step in order. Do not skip. Record the actual output for each verification. The lecture is complete only when all 9 steps pass.

---

## Step 1 — File Presence

Verify all 10 manifest files exist in `kubernetes/`:

```bash
ls -1 kubernetes/
```

**Expected output — all 10 files present:**
```
backend-deployment.yml
backend-service.yml
frontend-deployment.yml
frontend-service.yml
namespace.yml
postgres-configmap.yml
postgres-deployment.yml
postgres-pvc.yml
postgres-secret.yml
postgres-service.yml
```

**Pass criteria:** All 10 files listed, no extras beyond these.

---

## Step 2 — Build: Manifest Syntax

Validate YAML syntax for all manifests:

```bash
for f in kubernetes/*.yml; do
  kubectl apply --dry-run=client -f "$f" 2>&1 && echo "OK: $f" || echo "FAIL: $f"
done
```

**Pass criteria:** Every file prints `OK: kubernetes/[name].yml`. Zero FAIL lines.

---

## Step 3 — Stack Up: Cluster and Image Import

Verify the k3d cluster is running and images are imported:

```bash
k3d cluster list
kubectl get nodes
docker exec k3d-shoplist-server-0 crictl images 2>/dev/null | grep shoplist
```

**Pass criteria:**
- `k3d cluster list` shows `shoplist` cluster with status running
- `kubectl get nodes` shows at least 1 node in `Ready` state
- `crictl images` shows both `shoplist-backend:local` and `shoplist-frontend:local`

---

## Step 4 — Stack Health: All Pods Running

Verify all pods are in Running state with 1/1 containers ready:

```bash
kubectl get pods -n shoplist
kubectl get deployments -n shoplist
```

**Pass criteria:**
```
NAME                        READY   STATUS    RESTARTS   AGE
backend-[suffix]            1/1     Running   0          ...
frontend-[suffix]           1/1     Running   0          ...
postgres-[suffix]           1/1     Running   0          ...
```

All three pods: `1/1 Running`. Zero `CrashLoopBackOff`, `Pending`, or `ErrImageNeverPull`.

```
NAME       READY   UP-TO-DATE   AVAILABLE   AGE
backend    1/1     1            1           ...
frontend   1/1     1            1           ...
postgres   1/1     1            1           ...
```

All three Deployments: `1/1` available.

---

## Step 5 — Functional: API Endpoints

Verify the backend API is reachable and returns correct data:

```bash
# Health check
curl -s http://localhost:30080/api/health

# Add a product
curl -s -X POST http://localhost:30080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Laptop", "price": 999.00}'

# Retrieve products
curl -s http://localhost:30080/api/products
```

**Pass criteria:**
- `/api/health` returns `{"status": "ok"}` or equivalent
- POST returns the created product with an `id` field
- GET returns a JSON array containing the product just added

---

## Step 6 — Browser: Frontend UI

Open `http://localhost:30080` in a browser.

**Pass criteria:**
- Page loads without errors
- Product added in Step 5 is visible in the product list
- Adding a new product via the form succeeds and updates the list

---

## Step 7 — Persistence: Data Survives Pod Deletion

Confirm that deleting the postgres pod does not lose data:

```bash
# Record current product count
curl -s http://localhost:30080/api/products | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"

# Delete the pod
kubectl delete pod -n shoplist -l app=postgres

# Wait for replacement
kubectl get pods -n shoplist -w   # Ctrl-C when postgres pod is 1/1 Running again

# Confirm data intact
curl -s http://localhost:30080/api/products | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
```

**Pass criteria:** Product count before deletion equals product count after pod restart.

---

## Step 8 — Git State: Clean Commit

Verify Lecture 2 code is committed correctly:

```bash
git log --oneline -5
git diff HEAD
git status
```

**Pass criteria:**
- At least one commit with prefix `feat:`, `infra:`, or `config:` and message referencing Lecture 2 or Kubernetes
- `git diff HEAD` shows no unstaged changes to committed files
- `git status` shows working tree clean (or only untracked files that are deliberately not committed — e.g. `*.pptx`)
- No `kubernetes/postgres-secret.yml` in a committed state that also contains plaintext passwords (the file contains base64 values — this is acceptable in a local training environment, not in production)

---

## Step 9 — Knowledge: Quick Checks

Answer these without looking at any file:

1. What command lists all resources in the shoplist namespace?
2. What `imagePullPolicy` value prevents Kubernetes from pulling from a registry?
3. What happens to a PVC when you run `kubectl delete pod -n shoplist [postgres-pod]`?
4. What is the difference between a Secret and a ConfigMap?
5. Why does `nginx.conf` with `proxy_pass http://backend:5000/` work unchanged in Kubernetes?

**Model answers:**
1. `kubectl get all -n shoplist`
2. `Never`
3. Nothing — the PVC is not affected by pod deletion. The Deployment creates a replacement pod that mounts the same PVC.
4. Secrets are base64-encoded and RBAC-controlled, intended for passwords/tokens. ConfigMaps are plain text, readable by all, intended for non-sensitive configuration.
5. Kubernetes provides DNS resolution for Service names within the same namespace. The Service named `backend` resolves to its ClusterIP — identical behavior to Docker Compose service discovery.

**Pass criteria:** Answer all 5 without hesitation.

---

## Completion

When all 9 steps pass:

```bash
git add kubernetes/
git commit -m "infra: add Kubernetes manifests for local k3d deployment (Lecture 2)"
git checkout main
git merge feature/lecture-2
```
