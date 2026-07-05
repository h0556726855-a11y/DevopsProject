# Lecture 2 — Kubernetes: Local Deployment with k3d
## Student Guide

---

## Lecture Outcome (STRICT)

**What exists at the end of this lecture:**

| File | Kind | Purpose |
|------|------|---------|
| `kubernetes/namespace.yml` | Namespace | shoplist namespace |
| `kubernetes/postgres-secret.yml` | Secret | base64-encoded DB credentials |
| `kubernetes/postgres-configmap.yml` | ConfigMap | init.sql schema |
| `kubernetes/postgres-pvc.yml` | PersistentVolumeClaim | 1Gi postgres storage |
| `kubernetes/postgres-deployment.yml` | Deployment | postgres pod with readiness probe |
| `kubernetes/postgres-service.yml` | Service | ClusterIP at postgres:5432 |
| `kubernetes/backend-deployment.yml` | Deployment | Flask pod with readiness probe |
| `kubernetes/backend-service.yml` | Service | ClusterIP at backend:5000 |
| `kubernetes/frontend-deployment.yml` | Deployment | Nginx pod |
| `kubernetes/frontend-service.yml` | Service | NodePort at :30080 |

**What does NOT exist yet:**
- No GitLab CI/CD pipeline
- No registry-pushed images (images are still local only)
- No Terraform or cloud infrastructure
- No Ansible

**What you CAN do after this lecture:**
- Deploy the full ShopList application on a local Kubernetes cluster
- Apply manifests in the correct order using kubectl
- Inspect pods, services, and logs using kubectl
- Explain how Kubernetes differs from Docker Compose

**What you CANNOT do yet:**
- Deploy to a remote server or cloud
- Automatically build and push images from git commits
- Use registry-hosted images in manifests

---

## What You Will Build

The same three-tier ShopList application, running on Kubernetes instead of Docker Compose.

```
Browser :30080 → frontend (NodePort) → backend (ClusterIP) → postgres (ClusterIP)
                      ↓                      ↓                     ↓
                frontend-pod            backend-pod           postgres-pod
                                                                    ↓
                                                            postgres-pvc (1Gi)
```

**Application code is unchanged.** Zero modifications to app.py, nginx.conf, or any Dockerfile.

---

## What You Will Learn

- Why Kubernetes exists and what problem it solves beyond Docker Compose
- The difference between a Pod and a Deployment
- How Services provide stable DNS names for ephemeral pods
- How PersistentVolumeClaims separate storage lifecycle from pod lifecycle
- How to store credentials safely in Secrets (and why base64 is not encryption)
- How ConfigMaps mount configuration files into pods
- The correct apply order for dependent Kubernetes resources

---

## Prerequisites

Before starting, verify every item:

- [ ] k3d v5.6.0 is installed: `k3d version` shows output
- [ ] kubectl is installed: `kubectl version --client` shows output
- [ ] Docker Desktop is running with WSL2 integration enabled
- [ ] `shoplist-backend:local` and `shoplist-frontend:local` exist: `docker images | grep shoplist`
- [ ] You are on branch `feature/lecture-2`
- [ ] Port 30080 is not in use on your machine

**Install k3d (if not installed):**
```bash
curl -L "https://github.com/k3d-io/k3d/releases/download/v5.6.0/k3d-linux-amd64" \
  -o /tmp/k3d && chmod +x /tmp/k3d && sudo mv /tmp/k3d /usr/local/bin/k3d
```

**Install kubectl (if not installed):**
```bash
curl -LO "https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/
```

If any item fails, stop and resolve it before continuing.

---

## Part 1 — Core Concepts

Read this section before writing any files.

---

### Concept: Pod and Deployment

**What it is:**
A **Pod** is the smallest deployable unit in Kubernetes — one or more containers that share a network interface and storage. A **Deployment** declares a desired number of pod replicas and manages their lifecycle, creating replacement pods when existing ones fail.

**Why it exists:**
Docker Compose has no mechanism for restarting failed containers automatically (beyond the basic `restart:` policy, which only works on the same host). Kubernetes Deployments implement a continuous control loop: actual state is constantly compared to desired state. If a pod crashes, the Deployment creates a replacement. You no longer manage processes — you manage declarations.

**How it works:**
A Deployment creates a ReplicaSet, which creates and monitors Pods. The `spec.replicas` field declares how many pods should be running. The `selector.matchLabels` field defines which pods the Deployment manages. If any pod with matching labels is missing, the ReplicaSet creates a new one.

**Common mistake:**
Running bare pods instead of Deployments. Any pod you create without a Deployment is unmanaged — if it crashes, it stays crashed. In this course, every service (postgres, backend, frontend) uses a Deployment.

---

### Concept: Service

**What it is:**
A Service is a stable network endpoint that routes traffic to pods matching a label selector. Services provide fixed DNS names and IP addresses that remain constant even as pod IPs change.

**Why it exists:**
Pods are ephemeral. When a pod restarts, it gets a new IP address. If nginx needs to reach the backend and the backend pod IP changes on every restart, nginx would need to be reconfigured constantly. Services solve this by providing a stable name — `backend` — that always routes to the current backend pod.

**How it works:**
The Service selector matches pod labels. Traffic sent to the Service ClusterIP is forwarded to any pod with matching labels. The `nginx.conf` line `proxy_pass http://backend:5000/` works in Kubernetes exactly as it did in Docker Compose — Kubernetes provides DNS resolution for service names within the same namespace.

Service types:

| Type | Reachable From | Use in ShopList |
|---|---|---|
| ClusterIP (default) | Inside cluster only | postgres, backend |
| NodePort | Host machine via port 30000–32767 | frontend (:30080) |
| LoadBalancer | External IP (cloud) | Lecture 4 only |

**Common mistake:**
Referring to pods by IP address. Pod IPs are ephemeral and change on every restart. Always use the Service name for inter-pod communication.

---

### Concept: PersistentVolumeClaim

**What it is:**
A PersistentVolumeClaim (PVC) is a request for a specific amount and type of storage. Kubernetes binds the PVC to a PersistentVolume (actual storage), and the volume can be mounted into a pod. The PVC — and the data it holds — survives pod deletions.

**Why it exists:**
Container filesystems are ephemeral. When a pod is deleted, its filesystem is destroyed. For a database, this means all records are gone. PVCs separate the storage lifecycle from the pod lifecycle. The PVC exists independently of any pod — it persists until explicitly deleted.

**How it works:**
Declare a PVC with a size (1Gi) and access mode (ReadWriteOnce — one node at a time). Kubernetes binds it to available storage. Mount the PVC in the pod spec at the path where postgres stores its data (`/var/lib/postgresql/data`). When the pod is deleted, the PVC remains. When a replacement pod starts, it mounts the same PVC and finds all data intact.

**Common mistake:**
Confusing pod deletion with data loss. Deleting a pod in Kubernetes is safe — the Deployment creates a new pod that mounts the same PVC. To permanently delete the data, you must explicitly run `kubectl delete pvc postgres-pvc -n shoplist`. This is the Kubernetes equivalent of `docker compose down -v`.

---

### Concept: Secret

**What it is:**
A Secret is a Kubernetes object for storing sensitive data — passwords, tokens, and keys — in base64-encoded form, separated from application configuration and manageable with Kubernetes RBAC.

**Why it exists:**
Storing passwords in Deployment YAML, ConfigMaps, or environment variable plaintext makes them visible to anyone who can read those resources. Secrets can be access-controlled independently — only specific service accounts and users need read access to Secrets.

**How it works:**
Secret values are base64-encoded strings. They can be mounted as environment variables or as files. Multiple pods reference the same Secret by name. When a pod starts, the kubelet decodes the values and injects them as environment variables.

```bash
# Encode a value:
echo -n "shoppass" | base64      # → c2hvcHBhc3M=

# Decode a value:
echo "c2hvcHBhc3M=" | base64 -d  # → shoppass
```

**Common mistake:**
Thinking base64 is encryption. It is not. Anyone who can read the Secret object can decode every value in one command. The security comes from Kubernetes RBAC restricting who can access the Secret object — not from the encoding. Never commit Secret YAML files to git.

---

### Concept: ConfigMap

**What it is:**
A ConfigMap stores non-sensitive configuration data — text files, key-value pairs, configuration files — that can be mounted into pods as environment variables or as files.

**Why it exists:**
Hardcoding configuration inside container images means rebuilding the image for every configuration change. ConfigMaps allow images to be generic and reusable. Configuration is provided at runtime by mounting the ConfigMap into the pod.

**How it works:**
ConfigMap data is plain text. It can be mounted as environment variables or as files in the pod filesystem. In ShopList, `postgres-init` ConfigMap contains `init.sql`. It is mounted at `/docker-entrypoint-initdb.d` inside the postgres pod. PostgreSQL runs all `.sql` files in that directory on first startup.

**Common mistake:**
Putting secrets in ConfigMaps because it is simpler. ConfigMaps are readable by any pod and user in the namespace. Database passwords, API keys, and tokens must always go in Secrets, not ConfigMaps.

---

### Concept: Namespace

**What it is:**
A Namespace is a logical partition within a Kubernetes cluster that provides isolated scopes for names, access control, and resource quotas. All ShopList resources live in the `shoplist` namespace.

**Why it exists:**
Without namespaces, all resources in a cluster share one flat scope. In a shared cluster (multiple teams, multiple applications), this creates naming collisions and makes access control impossible at application granularity.

**How it works:**
Resources are created in a namespace and are only visible to other resources in the same namespace by default. kubectl commands require `-n shoplist` to target the correct namespace. The Service DNS name `postgres` works within the `shoplist` namespace. Cross-namespace DNS requires a fully qualified name.

**Common mistake:**
Forgetting `-n shoplist` on kubectl commands. Without it, kubectl targets the `default` namespace, which is empty. Nothing appears. Every kubectl command in this lecture must include `-n shoplist`.

---

## Part 2 — Step-by-Step Instructions

Write and verify each step before moving to the next.

---

### Step 1 — Create the k3d cluster

k3d creates a Kubernetes cluster inside Docker. The `--port` flag maps host port 30080 to the cluster's load balancer so the frontend NodePort service is accessible from your browser.

```bash
k3d cluster create shoplist --port "30080:30080@loadbalancer"
```

Verify the cluster is running and kubectl is configured:

```bash
kubectl cluster-info
kubectl get nodes
```

**Expected:** One node in `Ready` state.

---

### Step 2 — Import Docker images into k3d

k3d runs inside Docker and has its own image cache. Images on your host are not automatically available inside the cluster. Import the images built in Lecture 1:

```bash
k3d image import shoplist-backend:local shoplist-frontend:local -c shoplist
```

**Why this step is necessary:** The manifests use `imagePullPolicy: Never`, which tells Kubernetes to use only locally-available images and never attempt a registry pull. Without importing, every pod shows `ErrImageNeverPull`.

Verify images are imported:

```bash
docker exec k3d-shoplist-server-0 crictl images 2>/dev/null | grep shoplist
```

---

### Step 3 — Write and apply namespace.yml

Create `kubernetes/namespace.yml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shoplist
```

| Field | Purpose |
|---|---|
| `apiVersion: v1` | Core API group — applies to Namespaces, Services, Secrets, ConfigMaps, PVCs |
| `kind: Namespace` | Resource type |
| `metadata.name: shoplist` | The namespace name used in all subsequent manifests |

Apply immediately:
```bash
kubectl apply -f kubernetes/namespace.yml
# namespace/shoplist created
```

---

### Step 4 — Write postgres-secret.yml

Create `kubernetes/postgres-secret.yml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: shoplist
type: Opaque
data:
  POSTGRES_DB: c2hvcGxpc3Q=
  POSTGRES_USER: c2hvcHVzZXI=
  POSTGRES_PASSWORD: c2hvcHBhc3M=
```

| Key | Decoded Value | Encoded With |
|---|---|---|
| `POSTGRES_DB` | `shoplist` | `echo -n "shoplist" \| base64` |
| `POSTGRES_USER` | `shopuser` | `echo -n "shopuser" \| base64` |
| `POSTGRES_PASSWORD` | `shoppass` | `echo -n "shoppass" \| base64` |

The key names match exactly what the `postgres:15-alpine` image reads on startup.

```bash
kubectl apply -f kubernetes/postgres-secret.yml
```

---

### Step 5 — Write postgres-configmap.yml

Create `kubernetes/postgres-configmap.yml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-init
  namespace: shoplist
data:
  init.sql: |
    CREATE TABLE IF NOT EXISTS products (
        id     SERIAL PRIMARY KEY,
        name   VARCHAR(100) NOT NULL,
        price  NUMERIC(10, 2) NOT NULL
    );
```

This is the same `init.sql` from Lecture 1, now stored as a ConfigMap value. The postgres Deployment mounts this ConfigMap at `/docker-entrypoint-initdb.d`. PostgreSQL runs every `.sql` file in that directory on first startup.

```bash
kubectl apply -f kubernetes/postgres-configmap.yml
```

---

### Step 6 — Write postgres-pvc.yml

Create `kubernetes/postgres-pvc.yml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: shoplist
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

| Field | Value | Meaning |
|---|---|---|
| `accessModes: ReadWriteOnce` | RWO | One node can mount this volume at a time |
| `resources.requests.storage` | 1Gi | Claim 1 gibibyte of storage |

```bash
kubectl apply -f kubernetes/postgres-pvc.yml
kubectl get pvc -n shoplist
```

**Expected:** `postgres-pvc` shows status `Bound`. k3d provides a default StorageClass that fulfills PVC requests from the local filesystem.

---

### Step 7 — Write postgres-deployment.yml

Create `kubernetes/postgres-deployment.yml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: shoplist
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:15-alpine
          envFrom:
            - secretRef:
                name: postgres-secret
          ports:
            - containerPort: 5432
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "shopuser", "-d", "shoplist"]
            initialDelaySeconds: 5
            periodSeconds: 10
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
            - name: postgres-init
              mountPath: /docker-entrypoint-initdb.d
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: postgres-pvc
        - name: postgres-init
          configMap:
            name: postgres-init
```

| Field | Purpose |
|---|---|
| `replicas: 1` | One postgres pod at all times |
| `selector.matchLabels` | This Deployment manages pods labelled `app: postgres` |
| `template.metadata.labels` | Pods created by this Deployment get label `app: postgres` |
| `envFrom: secretRef` | Every key in `postgres-secret` becomes an environment variable |
| `readinessProbe` | Pod not marked Ready until `pg_isready` exits 0 — same as Lecture 1 healthcheck |
| `volumeMounts[0]` | PVC mounted at postgres data directory — persistent storage |
| `volumeMounts[1]` | ConfigMap mounted at init dir — init.sql runs on first start |

---

### Step 8 — Write postgres-service.yml

Create `kubernetes/postgres-service.yml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: shoplist
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
      targetPort: 5432
```

The Service name `postgres` becomes the DNS hostname. The backend uses `DB_HOST: postgres` which Kubernetes resolves to this Service's ClusterIP.

```bash
kubectl apply -f kubernetes/postgres-deployment.yml
kubectl apply -f kubernetes/postgres-service.yml
kubectl get pods -n shoplist -w    # wait for postgres to be 1/1 Running
```

---

### Step 9 — Write backend-deployment.yml

Create `kubernetes/backend-deployment.yml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: shoplist
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: shoplist-backend:local
          imagePullPolicy: Never
          env:
            - name: DB_HOST
              value: postgres
            - name: DB_NAME
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_DB
            - name: DB_USER
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_USER
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: POSTGRES_PASSWORD
          ports:
            - containerPort: 5000
          readinessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 10
```

| Field | Purpose |
|---|---|
| `imagePullPolicy: Never` | Use only locally imported images — do not pull from registry |
| `env.DB_HOST: postgres` | Service name — resolves to postgres ClusterIP via Kubernetes DNS |
| `valueFrom.secretKeyRef` | Read from Secret; note keys differ from Compose env var names |
| `readinessProbe.httpGet /health` | Pod not marked Ready until Flask /health returns 200 |

---

### Step 10 — Write backend-service.yml

Create `kubernetes/backend-service.yml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: shoplist
spec:
  selector:
    app: backend
  ports:
    - port: 5000
      targetPort: 5000
```

The Service name `backend` is what nginx.conf resolves with `proxy_pass http://backend:5000/`. This works identically to Docker Compose — different DNS mechanism, same result.

---

### Step 11 — Write frontend-deployment.yml and frontend-service.yml

Create `kubernetes/frontend-deployment.yml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: shoplist
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: shoplist-frontend:local
          imagePullPolicy: Never
          ports:
            - containerPort: 80
```

Create `kubernetes/frontend-service.yml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: shoplist
spec:
  type: NodePort
  selector:
    app: frontend
  ports:
    - port: 80
      targetPort: 80
      nodePort: 30080
```

| Field | Purpose |
|---|---|
| `type: NodePort` | Exposes the Service on the cluster node at a host-accessible port |
| `nodePort: 30080` | The specific port — mapped to host port 30080 by k3d's `--port` flag |

---

### Step 12 — Deploy everything and verify

Apply all remaining manifests in dependency order:

```bash
kubectl apply -f kubernetes/backend-deployment.yml
kubectl apply -f kubernetes/backend-service.yml
kubectl apply -f kubernetes/frontend-deployment.yml
kubectl apply -f kubernetes/frontend-service.yml
```

Verify all resources:

```bash
kubectl get all -n shoplist
```

**Expected:** All three pods `1/1 Running`. All three Deployments `1/1` available. Frontend Service shows `80:30080/TCP`.

Wait for all pods to be Ready, then test:

```bash
# Health check
curl http://localhost:30080/api/health

# Add a product
curl -s -X POST http://localhost:30080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Monitor", "price": 349.00}'

# Retrieve products
curl -s http://localhost:30080/api/products

# Open browser
# http://localhost:30080
```

Test persistence — delete the postgres pod and confirm data survives:

```bash
kubectl delete pod -n shoplist -l app=postgres

# Watch replacement start
kubectl get pods -n shoplist -w

# After new pod is Ready, data is still there:
curl http://localhost:30080/api/products
```

---

## Interview Questions

**Q: What is the difference between a Pod and a Deployment in Kubernetes?**
A: A Pod is a single running instance of one or more containers. A Deployment declares a desired number of pod replicas and manages their lifecycle — automatically creating replacement pods when existing ones fail. You always use Deployments, never bare pods, because bare pods have no restart mechanism.

**Q: What is the difference between a ClusterIP and a NodePort Service?**
A: ClusterIP (the default) makes a Service reachable only from inside the cluster — pods can reach each other by service name, but the host machine cannot reach the service directly. NodePort exposes the Service on a specific port (30000–32767) on the cluster node, making it reachable from the host machine. We use NodePort only for the frontend; backend and postgres use ClusterIP.

**Q: Why do we use a Secret instead of a ConfigMap for database credentials?**
A: Secrets can be access-controlled independently via Kubernetes RBAC — you can restrict which users and service accounts can read them. ConfigMaps are readable by any pod and user in the namespace. Note that base64 encoding is not encryption; the protection comes from access control, not from the encoding.

**Q: What is the purpose of a PVC, and what happens to it when a pod is deleted?**
A: A PVC is a request for persistent storage that exists independently of any pod. When a pod is deleted, the PVC is not deleted — the Deployment creates a replacement pod that mounts the same PVC and finds all data intact. To permanently delete the data, you must explicitly delete the PVC with `kubectl delete pvc`. This is the Kubernetes equivalent of `docker compose down -v`.

**Q: What does `imagePullPolicy: Never` do and why is it required with k3d?**
A: It tells Kubernetes to never attempt to pull the image from a registry — use only what is already available in the cluster's local image cache. With k3d, images must be imported into the cluster with `k3d image import` before deploying. Without this setting, Kubernetes tries to pull `shoplist-backend:local` from Docker Hub, fails, and the pod shows `ErrImageNeverPull` or `ImagePullBackOff`.
