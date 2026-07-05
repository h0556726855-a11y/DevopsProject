# Lecture 4 Validation Checklist

Work through each step in order. Mark each checkbox when the expected output matches.

---

### Step 1 — Terraform Files Exist

**Command:**
```bash
ls terraform/
```

**Expected Output:**
Four `.tf` files are listed, for example:
```
main.tf  variables.tf  outputs.tf  provider.tf
```

- [ ] Four `.tf` files are present in the `terraform/` directory

---

### Step 2 — AWS CLI Configured

**Command:**
```bash
aws sts get-caller-identity
```

**Expected Output:**
A JSON object containing your AWS account number:
```json
{
    "UserId": "...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:..."
}
```

- [ ] Command returns JSON with a non-empty `Account` field

---

### Step 3 — Cluster Exists in AWS

**Command:**
```bash
aws eks list-clusters --region eu-west-1
```

**Expected Output:**
```json
{
    "clusters": [
        "shoplist"
    ]
}
```

- [ ] `shoplist` appears in the `clusters` list

---

### Step 4 — kubectl Connected to the Cluster

**Command:**
```bash
kubectl cluster-info
```

**Expected Output:**
```
Kubernetes control plane is running at https://<cluster-endpoint>.gr7.eu-west-1.eks.amazonaws.com
```

- [ ] Output shows a live endpoint URL (not `localhost`)

---

### Step 5 — Node is Ready

**Command:**
```bash
kubectl get nodes
```

**Expected Output:**
```
NAME          STATUS   ROLES    AGE   VERSION
ip-10-0-...   Ready    <none>   ...   v1.28...
```

- [ ] Exactly 1 node is listed with `STATUS=Ready`

---

### Step 6 — Namespace Exists

**Command:**
```bash
kubectl get namespace shoplist
```

**Expected Output:**
```
NAME       STATUS   AGE
shoplist   Active   ...
```

- [ ] Namespace `shoplist` has `STATUS=Active`

---

### Step 7 — All Pods Running

**Command:**
```bash
kubectl get pods -n shoplist
```

**Expected Output:**
```
NAME                        READY   STATUS    RESTARTS   AGE
backend-...                 1/1     Running   0          ...
frontend-...                1/1     Running   0          ...
postgres-...                1/1     Running   0          ...
```

- [ ] Exactly 3 pods are listed
- [ ] All 3 pods show `STATUS=Running`

---

### Step 8 — LoadBalancer Has an External IP

**Command:**
```bash
kubectl get svc frontend -n shoplist
```

**Expected Output:**
```
NAME       TYPE           CLUSTER-IP   EXTERNAL-IP                                    PORT(S)        AGE
frontend   LoadBalancer   10.100...    abc123.eu-west-1.elb.amazonaws.com             80:...         ...
```

- [ ] `EXTERNAL-IP` column contains a DNS hostname (not `<pending>`)

---

### Step 9 — App Health Endpoint Responds

**Command:**
```bash
EXTERNAL_IP=$(kubectl get svc frontend -n shoplist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl -s http://$EXTERNAL_IP/api/health
```

**Expected Output:**
```json
{"status":"ok"}
```

- [ ] Response body is `{"status":"ok"}`

---

### Step 10 — App UI Loads in Browser

**Action:**
Open `http://<EXTERNAL-IP>` in a browser (use the DNS name from Step 8).

**Expected Output:**
The ShopList web interface loads — you can see a heading, an input field, and a list area.

- [ ] ShopList UI is visible in the browser at the LoadBalancer URL

---

### Step 11 — CRUD Operations Work

**Commands:**
```bash
EXTERNAL_IP=$(kubectl get svc frontend -n shoplist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Create an item
curl -s -X POST http://$EXTERNAL_IP/api/items \
  -H 'Content-Type: application/json' \
  -d '{"name":"lecture-4-test-item"}' | jq .

# Retrieve all items
curl -s http://$EXTERNAL_IP/api/items | jq .
```

**Expected Output:**
The POST returns the created item (with an `id` field). The GET returns an array that includes the item you just created:
```json
[
  { "id": 1, "name": "lecture-4-test-item" }
]
```

- [ ] POST creates the item and returns it with an `id`
- [ ] GET returns an array that includes the new item

---

### Step 12 — All 4 Pipeline Stages Passed

**Action:**
Open the GitLab project in a browser, navigate to **CI/CD > Pipelines**, and open the most recent pipeline run on `main`.

**Expected Output:**
All four stages show a green checkmark:
- `build-backend`
- `build-frontend`
- `verify-registry`
- `deploy`

- [ ] `build-backend` stage is green
- [ ] `build-frontend` stage is green
- [ ] `verify-registry` stage is green
- [ ] `deploy` stage is green

---

### Step 13 — Running Image Matches Latest Commit

**Commands:**
```bash
# Get the image tag currently running in the backend pod
kubectl describe pod -l app=backend -n shoplist | grep 'Image:'

# Get the short SHA of the latest commit on main
git log --oneline -1
```

**Expected Output:**
The image tag in `kubectl describe` ends with the same short SHA shown by `git log`. For example:

```
Image: registry.gitlab.com/org/shoplist/backend:a1b2c3d
a1b2c3d lecture-4: update frontend heading
```

- [ ] The image tag in the running pod matches the short commit SHA from `git log`
