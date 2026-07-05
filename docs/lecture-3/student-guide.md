# Lecture 3 — CI/CD Pipelines
## Student Guide

> **No CI/CD background? Start here:**
> Read [cicd-primer.md](cicd-primer.md) before this guide.
> It explains pipelines, stages, jobs, runners, and registries in plain language (15 min).

---

## Lecture Outcome (STRICT)

**What exists at the end of this lecture:**

| File | Change | Purpose |
|------|--------|---------|
| `.gitlab-ci.yml` | New | CI/CD pipeline (GitLab) — build + verify stages |
| `.github/workflows/build-and-push.yml` | New | CI/CD pipeline (GitHub Actions) — equivalent workflow |
| `kubernetes/backend-deployment.yml` | Modified | `image:` updated to registry path + SHA |
| `kubernetes/frontend-deployment.yml` | Modified | `image:` updated to registry path + SHA |

**What does NOT exist yet:**
- No Terraform files
- No Ansible playbooks
- No AWS infrastructure
- No automated Kubernetes deployment (pipeline builds and pushes; you still run kubectl apply manually in this lecture)
- No Helm charts

**What you CAN do after this lecture:**
- Trigger a Docker image build automatically by pushing a git commit
- Find tagged images in the GitLab Container Registry
- Trace any running Kubernetes pod back to the exact git commit that built its image
- Deploy to your k3d cluster using registry-hosted images instead of locally-imported images

**What you CANNOT do yet:**
- Deploy to a remote server or cloud
- Have the pipeline automatically apply your Kubernetes manifests
- Provision cloud infrastructure

---

## What You Will Build

A 3-stage CI/CD pipeline connected to the ShopList application.

```
git push (feature/lecture-3 or dev)
         ↓
.gitlab-ci.yml read by GitLab
         ↓
┌─────────────────────────────────────────────┐
│ stage: build                                │
│   build-backend  (docker build → backend)   │
│   build-frontend (docker build → frontend)  │
└─────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────┐
│ stage: test                                 │
│   test-backend   (dependency import check)  │
└─────────────────────────────────────────────┘
         ↓  (only on dev / main)
┌─────────────────────────────────────────────┐
│ stage: push                                 │
│   push-images    (docker login + push both) │
└─────────────────────────────────────────────┘
         ↓
GitLab Container Registry
registry.gitlab.com/[group]/devops-tikshuv-project/backend:[sha]
registry.gitlab.com/[group]/devops-tikshuv-project/frontend:[sha]
         ↓ (manual kubectl apply)
Kubernetes cluster — pods use registry images
```

**Application code is unchanged.** Zero modifications to app.py, nginx.conf, or any Dockerfile.

---

## What You Will Learn

- What CI/CD is and what problem it solves beyond manual docker build
- How a `.gitlab-ci.yml` file defines a pipeline with stages and jobs
- What Docker-in-Docker (dind) is and why CI jobs need it to run docker build
- How the GitLab Container Registry stores images by name and SHA tag
- Why SHA tagging is essential for traceability and rollback
- How to update Kubernetes manifests to pull images from a registry

---

## Prerequisites

Before starting, verify every item:

- [ ] GitLab account exists and project `devops-tikshuv-project` is accessible
- [ ] GitLab Container Registry is enabled: GitLab → Settings → General → Visibility → Container Registry → Enabled
- [ ] A runner is available: GitLab → Settings → CI/CD → Runners → at least one shared runner visible
- [ ] The k3d cluster from Lecture 2 is running: `kubectl get pods -n shoplist` shows 3 pods Running
- [ ] The application is accessible at `http://localhost:30080`
- [ ] You are on branch `feature/lecture-3` (`git checkout -b feature/lecture-3`)

If any item fails, stop and resolve it before continuing.

---

## Part 1 — Core Concepts

Read this section before writing any files.

---

### Concept: CI/CD

**What it is:**
CI/CD stands for Continuous Integration and Continuous Delivery. Continuous Integration means every git push automatically triggers a pipeline that builds and tests the code. Continuous Delivery means passing builds are automatically packaged and made available for deployment. Together, they replace the manual build-test-push sequence with an automated, auditable workflow.

**Why it exists:**
In the current state after Lecture 2, deploying a code change to Kubernetes requires four manual steps: `docker build`, `k3d image import`, editing the manifest, and `kubectl apply`. In a team setting, every developer runs this sequence independently, with no guarantee that everyone follows the same steps or uses the same base images. CI/CD centralizes and automates the build and push steps, so the only manual action is applying the manifest — and even that is automated in Lecture 4.

**How it works:**
GitLab reads `.gitlab-ci.yml` from the project root on every push. The file defines stages and jobs. GitLab dispatches jobs to available runners — processes that execute the job scripts in isolated containers. Each job runs in a fresh container, executes its script, and reports pass or fail. If any job fails, all subsequent stages are skipped.

**Common mistake:**
Treating CI/CD as "automatic deployment." After this lecture, the pipeline builds and pushes images automatically. Deploying to Kubernetes still requires a manual `kubectl apply`. CI (build + test) is not the same as CD (deploy). In this course, CD is introduced in Lecture 4.

---

### Concept: GitLab Runner

**What it is:**
A GitLab Runner is a process that picks up pipeline jobs from GitLab and executes them. Each job runs in a clean container environment defined by the job's `image:` field. GitLab.com provides shared runners available to all projects. Organizations can also register their own self-hosted runners.

**Why it exists:**
GitLab itself does not execute job scripts — it only orchestrates. Runners are the execution layer. By separating orchestration (GitLab server) from execution (runners), pipelines can run on any machine: a developer's laptop, a CI server, a Kubernetes node, or a cloud VM. The runner authenticates with GitLab, polls for available jobs, runs them, and reports results.

**How it works:**
When a pipeline is created, GitLab queues each job. An available runner picks up a job and starts a container using the `image:` value. It clones the repository into the container, executes the `script:` steps, and reports the exit code to GitLab. A zero exit code = pass. Any non-zero = fail. The container is destroyed after the job completes — no state persists between jobs.

**Common mistake:**
Expecting the image built in one job to be available in the next job. Each job runs in its own fresh container. The `docker build` result in `build-backend` does not persist to `test-backend`. This is why the test and push jobs rebuild the image before using it.

---

### Concept: Docker-in-Docker (dind)

**What it is:**
Docker-in-Docker is a configuration where a Docker daemon runs inside a Docker container. It enables jobs that need to run `docker build`, `docker push`, or `docker run` inside a CI pipeline — which itself runs inside a container.

**Why it exists:**
A GitLab CI job runs inside a container (specified by `image: docker:24`). The `docker:24` image includes the Docker CLI. But the CLI needs a Docker daemon to actually build images. By default, there is no daemon inside the job container. Adding `services: - docker:24-dind` starts a daemon as a sidecar service that the CLI connects to automatically.

**How it works:**
The `docker:24-dind` service starts a Docker daemon in a separate container alongside the job container. GitLab configures the `DOCKER_HOST` environment variable so the Docker CLI in the job container connects to this daemon. All `docker` commands in the script run against this daemon.

```
Job container (docker:24)
  - has Docker CLI
  - DOCKER_HOST points to dind sidecar
  - runs: docker build, docker run, docker push

dind sidecar container (docker:24-dind)
  - runs Docker daemon
  - accepts connections from job container
  - builds and stores images
```

**Common mistake:**
Forgetting `services: - docker:24-dind` on any job that uses docker commands. The symptom is immediate job failure with: `Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?`

---

### Concept: Container Registry

**What it is:**
A container registry is a server that stores and serves Docker images by name and tag. Images are pushed to the registry after building and pulled from the registry before running. GitLab includes a built-in container registry for every project at `registry.gitlab.com/[group]/[project]/[image-name]:[tag]`.

**Why it exists:**
Without a registry, Docker images exist only on the machine where they were built. A registry makes images portable: any machine with network access and appropriate credentials can pull and run the image. In a CI/CD pipeline, the runner builds the image and pushes it to the registry. The Kubernetes cluster then pulls from the registry when creating pods — eliminating the `k3d image import` step from Lecture 2.

**How it works:**
`docker login` authenticates to the registry. `docker push [image]:[tag]` uploads the image layers to the registry server. `docker pull [image]:[tag]` downloads them. The GitLab registry requires authentication via `$CI_REGISTRY_USER` and `$CI_REGISTRY_PASSWORD`, which GitLab injects automatically into every pipeline job.

**Common mistake:**
Forgetting to authenticate before pushing. Running `docker push` without a preceding `docker login` results in `denied: access forbidden`. The login step in the push job must always appear before the push commands.

---

### Concept: SHA Image Tagging

**What it is:**
SHA image tagging means using the git commit's short SHA (8 hexadecimal characters) as the Docker image tag, instead of a fixed label like `:latest`. GitLab provides this value automatically as `$CI_COMMIT_SHORT_SHA`.

**Why it exists:**
Every Docker image tag is a pointer. With `:latest`, that pointer is overwritten on every push. After ten pushes, you have ten images in the registry but they all share one tag — you cannot tell which code version corresponds to which image, and you cannot pull a specific previous version. With SHA tagging, every commit produces a permanent, uniquely identified image. The tag is the connection between the running container and the exact line of code that created it.

**How it works:**
GitLab sets `$CI_COMMIT_SHORT_SHA` to the first 8 characters of the git commit hash that triggered the pipeline. Setting `IMAGE_TAG: $CI_COMMIT_SHORT_SHA` in the variables block makes it available to all jobs. Every image built and pushed in the pipeline is tagged with this value.

```bash
# On commit abc12345:
docker push registry.gitlab.com/group/project/backend:abc12345

# On commit d4e56789:
docker push registry.gitlab.com/group/project/backend:d4e56789

# To roll back: update manifest image to :abc12345 and kubectl apply
```

**Common mistake:**
Using `:latest` as the tag. This is so common that the rule "never use `:latest`" is explicitly enforced in this pipeline via the `IMAGE_TAG` variable. Any pipeline that pushes `:latest` provides no traceability and no rollback capability.

---

## Part 2 — Step-by-Step Instructions

Write and verify each step before moving to the next.

---

### Step 1 — Enable Container Registry and verify runner

Before writing any YAML, confirm the GitLab project is configured correctly.

**Enable Container Registry:**

Go to GitLab → your project → Settings → General → expand "Visibility, project features, permissions" → confirm Container Registry is enabled (toggle should be on).

**Verify runner:**

Go to GitLab → your project → Settings → CI/CD → expand Runners. You should see at least one shared runner listed. If no runners appear, shared runners may be disabled for the group — contact the GitLab admin or go to Settings → CI/CD → Runners → enable shared runners.

You will not be able to run any pipeline without a runner.

---

### Step 2 — Create .gitlab-ci.yml with stages and variables

Create `.gitlab-ci.yml` at the project root:

```yaml
stages:
  - build
  - test
  - push

variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
  FRONTEND_IMAGE: $CI_REGISTRY_IMAGE/frontend
  IMAGE_TAG: $CI_COMMIT_SHORT_SHA
```

| Field | Value | Meaning |
|---|---|---|
| `stages` | build, test, push | Execution order; each stage runs only after the previous passes |
| `$CI_REGISTRY_IMAGE` | Injected by GitLab | Full registry path: `registry.gitlab.com/[group]/[project]` |
| `BACKEND_IMAGE` | `$CI_REGISTRY_IMAGE/backend` | Full path for the backend image |
| `IMAGE_TAG` | `$CI_COMMIT_SHORT_SHA` | 8-character git commit SHA; unique per commit |

---

### Step 3 — Add the build stage

Append to `.gitlab-ci.yml`:

```yaml
build-backend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/

build-frontend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $FRONTEND_IMAGE:$IMAGE_TAG app/frontend/
```

| Field | Value | Meaning |
|---|---|---|
| `stage: build` | build | This job belongs to the build stage |
| `image: docker:24` | docker:24 | Job container — has Docker CLI |
| `services: docker:24-dind` | docker:24-dind | Sidecar Docker daemon for building images |
| `docker build -t $BACKEND_IMAGE:$IMAGE_TAG` | — | Build the image tagged with registry path + SHA |
| `app/backend/` | — | Build context — path to the Dockerfile |

These two jobs run in parallel (both are in the `build` stage). If either fails, the test stage does not run.

---

### Step 4 — Add the test stage

Append to `.gitlab-ci.yml`:

```yaml
test-backend:
  stage: test
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/
    - docker run --rm $BACKEND_IMAGE:$IMAGE_TAG python -c "from flask import Flask; import psycopg2; print('All dependencies OK')"
```

This job rebuilds the backend image (fresh runner environment — the build stage's image is not available here) and runs a Python import check inside it.

| Command | Purpose |
|---|---|
| `docker build ...` | Rebuild the image in this job's environment |
| `docker run --rm` | Start a container and remove it when done |
| `python -c "from flask import Flask; import psycopg2; print(...)"` | Verify both dependencies are importable — confirms pip install succeeded |

**Expected output:**
```
All dependencies OK
```

If this line appears, the test passes. Any ImportError means the image is broken — pip install failed silently during docker build.

---

### Step 5 — Add the push stage

Append to `.gitlab-ci.yml`:

```yaml
push-images:
  stage: push
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/
    - docker build -t $FRONTEND_IMAGE:$IMAGE_TAG app/frontend/
    - docker push $BACKEND_IMAGE:$IMAGE_TAG
    - docker push $FRONTEND_IMAGE:$IMAGE_TAG
  only:
    - dev
    - main
```

| Field | Value | Meaning |
|---|---|---|
| `$CI_REGISTRY_USER` | Injected by GitLab | Your GitLab username |
| `$CI_REGISTRY_PASSWORD` | Injected by GitLab | Short-lived auth token for the registry |
| `$CI_REGISTRY` | Injected by GitLab | Registry hostname: `registry.gitlab.com` |
| `docker push` | — | Upload image to the registry |
| `only: dev, main` | — | This job only runs when the trigger branch is `dev` or `main` |

The complete `.gitlab-ci.yml` is now:
```yaml
stages:
  - build
  - test
  - push

variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
  FRONTEND_IMAGE: $CI_REGISTRY_IMAGE/frontend
  IMAGE_TAG: $CI_COMMIT_SHORT_SHA

build-backend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/

build-frontend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $FRONTEND_IMAGE:$IMAGE_TAG app/frontend/

test-backend:
  stage: test
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/
    - docker run --rm $BACKEND_IMAGE:$IMAGE_TAG python -c "from flask import Flask; import psycopg2; print('All dependencies OK')"

push-images:
  stage: push
  image: docker:24
  services:
    - docker:24-dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/
    - docker build -t $FRONTEND_IMAGE:$IMAGE_TAG app/frontend/
    - docker push $BACKEND_IMAGE:$IMAGE_TAG
    - docker push $FRONTEND_IMAGE:$IMAGE_TAG
  only:
    - dev
    - main
```

---

### Step 6 — Push and observe the pipeline on your feature branch

```bash
git add .gitlab-ci.yml
git commit -m "ci: add GitLab CI/CD pipeline with build, test, push stages"
git push origin feature/lecture-3
```

Open GitLab → CI/CD → Pipelines. You should see a pipeline running for your commit.

**Expected pipeline result on feature/lecture-3:**
- `build-backend` → passed
- `build-frontend` → passed
- `test-backend` → passed
- `push-images` → skipped (feature branch is not in `only: dev, main`)

All three stages show green checkmarks. Push is correctly skipped. This is the expected behavior.

Click into any job to see its full log output.

---

### Step 7 — Merge to dev and verify registry images

Merge to dev to trigger the full pipeline including push:

```bash
git checkout dev
git merge feature/lecture-3
git push origin dev
```

Watch the new pipeline — all 4 jobs should pass including `push-images`.

After the push-images job completes, verify the registry:

GitLab → Deploy → Container Registry

You should see two image repositories:
- `backend`
- `frontend`

Each with one tag — the 8-character SHA from your commit.

To find the SHA:
```bash
git log --oneline -1
# Example output: abc12345 ci: add GitLab CI/CD pipeline...
```

The SHA (`abc12345`) is the image tag in the registry.

---

### Step 8 — Update the Kubernetes manifests

Get the full registry path from GitLab → Deploy → Container Registry. Copy the image name for `backend`.

Format: `registry.gitlab.com/[your-group]/devops-tikshuv-project/backend`

Edit `kubernetes/backend-deployment.yml`. Change:
```yaml
image: registry.gitlab.com/YOUR_GROUP/devops-tikshuv-project/backend:YOUR_SHA
imagePullPolicy: Always
```

Replace `YOUR_GROUP` with your GitLab group or username (visible in the registry URL).
Replace `YOUR_SHA` with the 8-character SHA from Step 7.

Example (replace with your actual values):
```yaml
image: registry.gitlab.com/rivky9505/devops-tikshuv-project/backend:abc12345
imagePullPolicy: Always
```

Edit `kubernetes/frontend-deployment.yml`. Apply the same pattern for the frontend image:
```yaml
image: registry.gitlab.com/YOUR_GROUP/devops-tikshuv-project/frontend:YOUR_SHA
imagePullPolicy: Always
```

**Why `imagePullPolicy: Always` instead of `Never`:**
`Never` told Kubernetes to use only locally-imported images. Now that images live in the registry, `Always` tells Kubernetes to pull from the registry every time a pod starts. Since the tag is a specific SHA that never changes, the pull is a no-op after the first download — the image is cached locally. But the explicit pull ensures the cluster always has the correct version.

---

### Step 9 — Apply and verify

Apply the updated manifests:

```bash
kubectl apply -f kubernetes/backend-deployment.yml
kubectl apply -f kubernetes/frontend-deployment.yml
```

Watch both deployments roll out:

```bash
kubectl rollout status deployment/backend -n shoplist
kubectl rollout status deployment/frontend -n shoplist
```

**Expected:**
```
deployment "backend" successfully rolled out
deployment "frontend" successfully rolled out
```

Verify the pod is using the registry image:

```bash
kubectl describe pod -n shoplist -l app=backend | grep Image:
```

**Expected:** `Image: registry.gitlab.com/[group]/devops-tikshuv-project/backend:[sha]`

Test the application:

```bash
curl http://localhost:30080/api/health
```

**Expected:** `{"status": "ok"}`

Open `http://localhost:30080` in the browser — the application works identically with the registry-hosted image.

---

## Interview Questions

**Q: What is the difference between CI and CD?**
A: CI — Continuous Integration — means every git commit triggers an automated build and test. The goal is to continuously verify the codebase builds and basic tests pass. CD — Continuous Delivery — means if CI passes, the artifact is automatically packaged and pushed to a registry or deployed to an environment. In this lecture we implement CI (build + test) and the first half of CD (push to registry). Automated deployment to Kubernetes is CD's second half, introduced in Lecture 4.

**Q: What does `$CI_COMMIT_SHORT_SHA` contain, and why use it instead of `:latest`?**
A: It contains the first 8 characters of the git commit hash that triggered the pipeline. Using it as the image tag means every commit produces a uniquely identified, permanent image. With `:latest`, every push overwrites the same tag. After 10 pushes, 10 images exist but they all share one tag — you cannot identify which code version is running, and you cannot roll back to a specific earlier version. SHA tagging makes the image tag a direct link to the git commit.

**Q: What is Docker-in-Docker, and why is it required in a GitLab pipeline job that runs docker build?**
A: Docker-in-Docker is a Docker daemon running inside a Docker container. A GitLab CI job runs inside a container (specified by `image: docker:24`), which includes the Docker CLI. But running `docker build` requires a Docker daemon — a background process — which the job container does not have by default. Adding `services: - docker:24-dind` starts a daemon as a sidecar container that the CLI connects to. Without it, `docker build` fails with "Cannot connect to the Docker daemon."

**Q: After pushing a new image to the GitLab Registry, what is the minimum sequence of commands to update the running Kubernetes pod?**
A: (1) Update the `image:` field in the deployment YAML to the new registry path and SHA tag. (2) `kubectl apply -f kubernetes/[service]-deployment.yml` to submit the change to the cluster. (3) `kubectl rollout status deployment/[service] -n shoplist` to confirm the new pod starts successfully. Kubernetes pulls the new image and replaces the running pod. If the new image fails to start, Kubernetes keeps the previous pod running.

**Q: What is the purpose of the test stage in this pipeline, and why does it come before the push stage?**
A: The test stage verifies the image is internally correct before it reaches the registry. It rebuilds the backend image and runs a Python import check — `from flask import Flask; import psycopg2` — inside the container. If either import fails, it means pip install did not install the dependency correctly and the image is broken. The test stage comes before push because the fundamental guarantee of a CI pipeline is: only valid artifacts enter the registry. A broken image in the registry could be pulled by any team member or any cluster.

---

## Appendix G — GitHub Actions (Alternative to GitLab CI)

Use this appendix if your project is hosted on GitHub instead of GitLab.
The concepts are identical. The file location, YAML syntax, and registry URL differ.
See [cicd-primer.md](cicd-primer.md) for the side-by-side concept comparison.

---

### G1 — What is already in the repo

The workflow file already exists at `.github/workflows/build-and-push.yml`.
You do not need to write it from scratch — it is equivalent to `.gitlab-ci.yml`.

| | GitLab CI | GitHub Actions |
|---|---|---|
| Pipeline file | `.gitlab-ci.yml` (project root) | `.github/workflows/build-and-push.yml` |
| Registry | `registry.gitlab.com/[group]/[project]` | `ghcr.io/[owner]` |
| Short SHA variable | `$CI_COMMIT_SHORT_SHA` (auto) | `${GITHUB_SHA::8}` (set manually via `$GITHUB_ENV`) |
| Credentials | `$CI_REGISTRY_USER` / `$CI_REGISTRY_PASSWORD` (auto) | `${{ secrets.GITHUB_TOKEN }}` (auto) |
| Docker daemon | `services: docker:24-dind` required | included in `ubuntu-latest` runner |

---

### G2 — Enable GitHub Actions and required permissions

GitHub Actions is enabled by default on all repositories.

**Enable package write permission:**
GitHub → your repo → Settings → Actions → General → Workflow permissions → select **"Read and write permissions"** → Save.

This allows the workflow to push images to `ghcr.io` using the auto-injected `GITHUB_TOKEN`.

Without this, the push step fails with `denied: installation not allowed to Write organization package`.

---

### G3 — Verify the workflow file

Open `.github/workflows/build-and-push.yml`. The three jobs are:

```
build-backend   ──┐
                  ├─ run simultaneously (both in no-stage parallel)
build-frontend  ──┘
       ↓
verify-registry  (needs: both build jobs)
```

The workflow triggers on pushes to `main` that change files under `app/backend/`, `app/frontend/`, or the workflow file itself. It can also be triggered manually from the Actions tab (`workflow_dispatch:`).

---

### G4 — Push and observe the pipeline

```bash
git add .github/workflows/build-and-push.yml
git commit -m "ci: add GitHub Actions workflow for build and push"
git push origin main
```

Open GitHub → your repo → Actions tab. You should see a workflow run for your commit.

**Expected result:**
- `build-backend` → passed
- `build-frontend` → passed
- `verify-registry` → passed (pulls both images to confirm they exist)

Click any job to see its full log, including the pushed image URL.

---

### G5 — Find images in ghcr.io

After the workflow passes, images are stored in the GitHub Container Registry.

GitHub → your profile or org → Packages

You should see:
- `shoplist-backend`
- `shoplist-frontend`

Each tagged with the 8-character commit SHA.

To find the SHA:
```bash
git log --oneline -1
# Example: a1b2c3d4 ci: add GitHub Actions workflow...
```

The tag is `a1b2c3d4`.

Full image URL format:
```
ghcr.io/[your-github-username]/shoplist-backend:a1b2c3d4
ghcr.io/[your-github-username]/shoplist-frontend:a1b2c3d4
```

---

### G6 — Update Kubernetes manifests

Edit `kubernetes/backend-deployment.yml`:

```yaml
image: ghcr.io/YOUR_GITHUB_USERNAME/shoplist-backend:YOUR_SHA
imagePullPolicy: Always
```

Edit `kubernetes/frontend-deployment.yml`:

```yaml
image: ghcr.io/YOUR_GITHUB_USERNAME/shoplist-frontend:YOUR_SHA
imagePullPolicy: Always
```

Replace `YOUR_GITHUB_USERNAME` with your GitHub username (lowercase).
Replace `YOUR_SHA` with the 8-character SHA from G5.

---

### G7 — Make ghcr.io images public (simplest option) or create a pull secret

By default, `ghcr.io` packages are private. Kubernetes needs credentials to pull them.

**Option A — Make packages public (easiest for local development):**

GitHub → your profile → Packages → select `shoplist-backend` → Package settings → Change visibility → Public. Repeat for `shoplist-frontend`.

Once public, your k3d or minikube cluster can pull without credentials.

**Option B — Create an imagePullSecret (required for private packages):**

```bash
# Create a personal access token at GitHub → Settings → Developer Settings
# → Personal access tokens → Tokens (classic) → read:packages scope

kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_PERSONAL_ACCESS_TOKEN \
  -n shoplist
```

Then add to each deployment spec:
```yaml
spec:
  imagePullSecrets:
    - name: ghcr-secret
  containers:
    - name: backend
      image: ghcr.io/YOUR_GITHUB_USERNAME/shoplist-backend:YOUR_SHA
```

---

### G8 — Apply and verify

Same as the GitLab path:

```bash
kubectl apply -f kubernetes/backend-deployment.yml
kubectl apply -f kubernetes/frontend-deployment.yml
kubectl rollout status deployment/backend -n shoplist
kubectl rollout status deployment/frontend -n shoplist
```

Verify the pod is using the ghcr.io image:

```bash
kubectl describe pod -n shoplist -l app=backend | grep Image:
# Expected: Image: ghcr.io/[username]/shoplist-backend:[sha]
```

Test the application:

```bash
curl http://localhost:30080/api/health
# Expected: {"status": "ok"}
```

---

### G9 — Key differences to remember

| Situation | GitLab | GitHub |
|---|---|---|
| Pipeline file missing | `.gitlab-ci.yml` not found error | workflow in `.github/workflows/` not triggered |
| No short SHA variable | `$CI_COMMIT_SHORT_SHA` always available | must set `SHORT_SHA=${GITHUB_SHA::8}` via `$GITHUB_ENV` |
| Registry auth fails | check runner has CI/CD → Settings → Variables | check workflow has `permissions: packages: write` |
| Image pull fails in k8s | check `imagePullPolicy: Always` and registry path | check package is public OR imagePullSecret is configured |
