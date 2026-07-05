# Lecture 4 Exercises — EKS, Terraform, and the Full Pipeline

## Exercise 1 — Explore the Live EKS Cluster

**Difficulty:** Easy

### Task

Use the AWS CLI and kubectl to inspect the live EKS cluster and confirm all components are healthy.

Run each of the following commands and record the output:

```bash
aws eks list-clusters --region eu-west-1
kubectl get nodes
kubectl get pods -n shoplist
kubectl get svc -n shoplist
```

### Expected Result

- `aws eks list-clusters` returns a JSON object listing `shoplist` under `"clusters"`
- `kubectl get nodes` shows exactly 1 node with `STATUS=Ready`
- `kubectl get pods -n shoplist` shows 3 pods all in `Running` state
- `kubectl get svc -n shoplist` shows the `frontend` service with an `EXTERNAL-IP` that is a DNS hostname (not `<pending>`)

### Validation Command

```bash
kubectl get svc frontend -n shoplist
```

**Pass criteria:** The `EXTERNAL-IP` column contains a DNS name (ends in `.elb.amazonaws.com`), not `<pending>`.

---

## Exercise 2 — Push a Change and Watch the Full Automated Deploy

**Difficulty:** Medium

### Task

Make a small visible change to the frontend, push it, and verify the full CI/CD pipeline deploys it automatically to EKS.

1. Open a file in `app/frontend/` — for example the main page title or a heading in the HTML/JSX source.
2. Change the text to something you can recognise (e.g. add your name or the date).
3. Commit and push to `main`:

```bash
git add app/frontend/
git commit -m "lecture-4: update frontend heading"
git push origin main
```

4. Open the GitLab pipeline UI and watch all 4 stages complete:
   - `build-backend`
   - `build-frontend`
   - `verify-registry`
   - `deploy`
5. Once the pipeline is green, open the LoadBalancer URL in a browser and confirm your text change is visible.

### Expected Result

- All 4 pipeline stages show a green checkmark
- The change you made appears at `http://EXTERNAL-IP` in the browser

### Validation Command

```bash
# Get the LoadBalancer URL
kubectl get svc frontend -n shoplist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

Open that URL in a browser.

**Pass criteria:** Pipeline is fully green AND the updated text is visible in the browser.

---

## Exercise 3 — Verify Data Persists After Pod Restart on EKS

**Difficulty:** Medium

### Task

Confirm that the Postgres data volume (backed by an EBS PersistentVolumeClaim) survives a pod restart.

1. Open the app at the LoadBalancer URL and add 3 shopping items via the browser UI.
2. Delete the Postgres pod to simulate a crash:

```bash
kubectl delete pod -l app=postgres -n shoplist
```

3. Wait for Kubernetes to reschedule and restart the pod:

```bash
kubectl wait pod -l app=postgres -n shoplist \
  --for=condition=Ready \
  --timeout=60s
```

4. Reload the browser and verify your 3 items are still listed.

### Expected Result

- The pod restarts automatically (Kubernetes reschedules it)
- All 3 items you added before the restart are still present after it

### Validation Command

```bash
# Confirm the pod is Running again
kubectl get pods -l app=postgres -n shoplist

# Confirm items are still in the API
EXTERNAL_IP=$(kubectl get svc frontend -n shoplist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl -s http://$EXTERNAL_IP/api/items
```

**Pass criteria:** Pod status is `Running` and the API returns the 3 items you created before the restart. The PVC and the underlying EBS volume preserved the data.

---

## Exercise 4 (Optional Bonus) — Inspect What Terraform Created in AWS

**Difficulty:** Bonus / Exploratory

### Task

Log into the AWS Console and trace the infrastructure that Terraform provisioned. You are looking for evidence that the Terraform code in `terraform/` produced real AWS resources.

Navigate to each section of the AWS Console (`eu-west-1` region):

| Console Section | What to find |
|---|---|
| **EKS** | A cluster named `shoplist` |
| **EC2 > Instances** | 1 instance of type `t3.micro` (the worker node) |
| **VPC > Subnets** | 2 public subnets, each in a different Availability Zone |
| **EC2 > Load Balancers** | 1 Classic Load Balancer created by the `frontend` Kubernetes service |

Answer the following questions (write your answers in a comment or a note):

1. What is the full DNS name of the Classic ELB?
2. Which two Availability Zones are the public subnets in?
3. What is the Instance ID of the worker node?

### Validation

Take a screenshot of each Console page showing the resources above, or write a short description of what you found. Compare your ELB DNS name against the output of:

```bash
kubectl get svc frontend -n shoplist -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

**Pass criteria:** The ELB DNS name, the two subnet AZs, and the single `t3.micro` node all match what the Terraform files in `terraform/` declare.
