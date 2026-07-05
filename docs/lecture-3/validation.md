# Lecture 3 — GitLab CI/CD
## Validation Checklist

**Rules:**
1. Run every step in order. Do not skip steps.
2. Each step must produce the exact expected output before proceeding to the next.
3. If a step fails, stop and resolve it before continuing.
4. Complete the merge in Step 9 exactly as written — do not merge to `main`.

---

### Step 1 — Verify .gitlab-ci.yml exists and has 4 jobs

```bash
cat .gitlab-ci.yml | grep "stage:"
```

**Expected output:**
```
  stage: build
  stage: build
  stage: test
  stage: push
```

Four `stage:` lines — one per job. If fewer than 4, open the file and verify all 4 jobs are present.

---

### Step 2 — Verify both Kubernetes manifests use registry images

```bash
grep "image:" kubernetes/backend-deployment.yml kubernetes/frontend-deployment.yml
```

**Expected output:**
```
kubernetes/backend-deployment.yml:          image: registry.gitlab.com/YOUR_GROUP/devops-tikshuv-project/backend:YOUR_SHA
kubernetes/frontend-deployment.yml:          image: registry.gitlab.com/YOUR_GROUP/devops-tikshuv-project/frontend:YOUR_SHA
```

Both files must show `registry.gitlab.com` in the image path, not `shoplist-backend:local` or `shoplist-frontend:local`.

---

### Step 3 — Verify imagePullPolicy is Always in both manifests

```bash
grep "imagePullPolicy" kubernetes/backend-deployment.yml kubernetes/frontend-deployment.yml
```

**Expected output:**
```
kubernetes/backend-deployment.yml:          imagePullPolicy: Always
kubernetes/frontend-deployment.yml:          imagePullPolicy: Always
```

Both must show `Always`. If either shows `Never`, update the file.

---

### Step 4 — Push to feature branch and verify build + test pass

```bash
git push origin feature/lecture-3
```

Open GitLab → CI/CD → Pipelines. Wait for the pipeline on `feature/lecture-3` to complete.

**Expected result:**
- `build-backend` → passed
- `build-frontend` → passed
- `test-backend` → passed
- `push-images` → skipped

Three green, one skipped. If `push-images` shows "passed" instead of "skipped", the `only:` block is missing from the job.

---

### Step 5 — Verify test-backend log output

Click into the `test-backend` job in the GitLab UI.

**Expected line in the log:**
```
All dependencies OK
```

This confirms Flask and psycopg2 were correctly installed in the backend image. If this line is absent and the job still passed, the `docker run` command may not be running the import check correctly.

---

### Step 6 — Merge to dev and verify push-images runs

```bash
git checkout dev
git merge feature/lecture-3
git push origin dev
```

Open GitLab → CI/CD → Pipelines. Wait for the pipeline on `dev` to complete.

**Expected result:**
- `build-backend` → passed
- `build-frontend` → passed
- `test-backend` → passed
- `push-images` → passed

All 4 jobs green. If `push-images` fails with an authentication error, verify the GitLab Container Registry is enabled in Settings → General → Visibility.

---

### Step 7 — Verify images appear in Container Registry

Open GitLab → Deploy → Container Registry.

**Expected:**
- Repository `backend` exists with at least one tag
- Repository `frontend` exists with at least one tag
- The tag on each image is 8 hexadecimal characters

Confirm the tag matches your latest commit SHA:
```bash
git log --oneline -1
```

The 8-character prefix of the output must match the tag shown in the registry.

---

### Step 8 — Apply manifests and verify cluster uses registry images

```bash
kubectl apply -f kubernetes/backend-deployment.yml
kubectl apply -f kubernetes/frontend-deployment.yml
kubectl rollout status deployment/backend -n shoplist
kubectl rollout status deployment/frontend -n shoplist
```

**Expected output:**
```
deployment "backend" successfully rolled out
deployment "frontend" successfully rolled out
```

Verify the pod image:
```bash
kubectl describe pod -n shoplist -l app=backend | grep Image:
```

**Expected:** The `Image:` field contains `registry.gitlab.com/...`, not `shoplist-backend:local`.

Test the application:
```bash
curl http://localhost:30080/api/health
```

**Expected:** `{"status": "ok"}`

---

### Step 9 — Final commit and merge

```bash
git add .gitlab-ci.yml kubernetes/backend-deployment.yml kubernetes/frontend-deployment.yml
git commit -m "ci: add GitLab CI/CD pipeline and update manifests to use registry images"
git checkout dev
git merge feature/lecture-3
git push origin dev
```

**Expected:** `git push origin dev` completes without errors. Do not merge to `main`.

Verify the merge:
```bash
git log --oneline -3
```

**Expected:** The most recent commit on `dev` is the Lecture 3 work.

---

## Knowledge Check

**Question 1:** The `push-images` job has `only: dev, main`. A student pushes to `feature/lecture-3` and sees that `push-images` is shown as "skipped" in the pipeline. Is this correct behavior or a bug?

**Answer:** Correct behavior. The `only:` keyword restricts a job to run only on the listed branches. On any other branch, the job is skipped. Skipping is intentional — feature branches build and test but never push to the registry. Only merged, reviewed code on `dev` or `main` produces registry images. If the student sees "skipped," the pipeline is working as designed.

---

**Question 2:** A student removes `services: - docker:24-dind` from the `build-backend` job. What is the exact error they will see, and at which line of the job script will it occur?

**Answer:** The error occurs at the first `docker build` command. The error message is: `Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?` Without the `docker:24-dind` service, there is no Docker daemon for the CLI to connect to. The job fails immediately on the first `docker` command.

---

**Question 3:** After running the full pipeline on `dev`, a student opens GitLab → Deploy → Container Registry and sees two image repositories. What determines the tag on each image?

**Answer:** The tag is the value of `$CI_COMMIT_SHORT_SHA`, which is the first 8 characters of the git commit hash that triggered the pipeline. Each commit that runs the full pipeline (on `dev` or `main`) produces a new tag. The tag is permanent — it is never overwritten. The student can verify the tag matches their commit by running `git log --oneline -1` and comparing the 8-character SHA prefix.

---

**Question 4:** After updating `kubernetes/backend-deployment.yml` with the registry image path and running `kubectl apply`, a student sees the pod in `ImagePullBackOff` state. List two possible causes.

**Answer:** (1) The image path or SHA tag in the manifest is incorrect — it does not match the actual path in the registry. Fix: copy the exact image path from GitLab → Deploy → Container Registry. (2) The Kubernetes cluster cannot reach the GitLab Container Registry due to a network filter or proxy restriction. Fix: run `docker pull registry.gitlab.com/[group]/[project]/backend:[sha]` from WSL2 to test connectivity. If the pull fails from the command line, the issue is network access, not the manifest.
