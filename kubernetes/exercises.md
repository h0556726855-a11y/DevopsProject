# Lecture 2 — Exercises
## Kubernetes: Local Deployment with k3d

---

**Instructions:**
- Complete exercises in order
- Do not look at the student guide unless you are stuck
- Verify each exercise before moving to the next
- All kubectl commands require `-n shoplist` unless noted
- Work on branch `feature/lecture-2`

---

## Exercise 1 — Inspect a Running Cluster (Easy)

**Task:**
With the ShopList application running on Kubernetes, answer the following questions using only kubectl commands. Do not look at the YAML files — read the live state from the cluster.

1. List all pods in the shoplist namespace and identify their full names (including the generated suffix)
2. View the live logs of the backend pod
3. Find all environment variables set inside the backend pod
4. Find the ClusterIP address assigned to the postgres Service
5. Describe the postgres pod and identify the readiness probe definition

**Commands to research:**
`kubectl get pods`, `kubectl logs`, `kubectl exec`, `kubectl describe`, `kubectl get services`

**Expected results:**
1. Three pods with names: `postgres-[suffix]`, `backend-[suffix]`, `frontend-[suffix]`
2. Backend logs show Flask startup: `* Running on all addresses (0.0.0.0)`
3. Environment variables include `DB_HOST=postgres`, `DB_NAME=shoplist`, `DB_USER=shopuser`
4. A ClusterIP in the `10.x.x.x` range
5. Readiness probe section shows exec command: `pg_isready -U shopuser -d shoplist`

**Validation:**
```bash
kubectl get pods -n shoplist
kubectl logs -n shoplist deployment/backend
kubectl exec -n shoplist deployment/backend -- env | grep DB_
kubectl get services -n shoplist
kubectl describe pod -n shoplist -l app=postgres | grep -A 10 "Readiness"
```

---

## Exercise 2 — Break and Fix: Remove the Readiness Probe (Medium)

**Task:**
Make the following deliberate change to `kubernetes/postgres-deployment.yml`:

Remove the entire `readinessProbe:` block from the postgres container spec.

Then:
1. Apply the change: `kubectl apply -f kubernetes/postgres-deployment.yml`
2. Watch what happens: `kubectl get pods -n shoplist -w`
3. Check backend logs immediately after the postgres pod restarts: `kubectl logs -n shoplist deployment/backend`
4. Look for connection errors — does the backend fail to connect before postgres is ready?

Then restore the readiness probe and re-apply.

**What you are observing:**
Without a readiness probe, the postgres pod is marked Ready as soon as the container starts — before PostgreSQL has finished initializing. The backend may attempt its database connection before PostgreSQL accepts it. Kubernetes has no healthcheck equivalent here without the probe — the backend retries via CrashLoopBackOff or connection errors.

With the readiness probe, the postgres pod is only marked Ready after `pg_isready` succeeds. The backend's readiness probe also delays traffic until the backend successfully connects.

**Expected results:**
- Without probe: backend logs may show `psycopg2.OperationalError: could not connect to server` or similar connection errors during startup
- With probe: backend starts cleanly — postgres is ready before traffic is routed to it

**Validation:**
```bash
# After removing probe and re-applying:
kubectl describe pod -n shoplist -l app=postgres | grep -i readiness

# After restoring:
kubectl describe pod -n shoplist -l app=postgres | grep -A 6 "Readiness"
```

---

## Exercise 3 — Observe PVC Persistence (Medium)

**Task:**
Test the data persistence guarantee that a PVC provides — specifically that deleting a pod does NOT delete the data.

1. Add a product via the browser or curl: `http://localhost:30080`
2. Find the postgres pod name: `kubectl get pods -n shoplist`
3. Delete the postgres pod: `kubectl delete pod -n shoplist [postgres-pod-name]`
4. Watch the Deployment create a new pod: `kubectl get pods -n shoplist -w`
5. Wait for the new pod to be Running and Ready
6. Open `http://localhost:30080` — confirm the product is still there

Then observe what data loss actually looks like:
7. Delete the PVC: `kubectl delete pvc postgres-pvc -n shoplist`
8. Delete and recreate the postgres Deployment to force a new pod
9. Open the browser — confirm the product is gone

Then restore the PVC by re-applying `kubernetes/postgres-pvc.yml` and restarting the postgres Deployment.

**What you are learning:**
In Kubernetes, the data lifecycle is separated from the pod lifecycle. Deleting a pod is safe — the Deployment creates a replacement that mounts the same PVC. Deleting the PVC is destructive — data is permanently lost. This is the equivalent of `docker compose down -v`.

**Expected results:**
- After pod deletion: data survives (same PVC, new pod, same data)
- After PVC deletion: data is gone (new PVC, fresh database, empty product list)

**Validation:**
```bash
kubectl get pvc -n shoplist                 # confirm PVC status (Bound)
kubectl get pods -n shoplist                # confirm postgres pod restarted
curl http://localhost:30080/api/products    # confirm data state
```

---

## Bonus Exercise — Scale the Backend (Optional)

**Task:**
Scale the backend Deployment to 3 replicas and observe how Kubernetes manages the change.

1. Scale up: `kubectl scale deployment backend --replicas=3 -n shoplist`
2. Watch pods start: `kubectl get pods -n shoplist -w`
3. Confirm 3 backend pods are running: `kubectl get pods -n shoplist -l app=backend`
4. Send several requests and observe load distribution in logs
5. Scale back to 1: `kubectl scale deployment backend --replicas=1 -n shoplist`
6. Confirm the application still works at `http://localhost:30080`

**What you are observing:**
Kubernetes creates two additional backend pods within seconds. The ClusterIP Service automatically load-balances requests across all 3 pods. Scaling down terminates 2 pods gracefully. No downtime. No configuration change required in nginx or any other service.

**This exercise is not required to pass the lecture.**
It demonstrates horizontal scaling — a concept that does not exist in Docker Compose.
