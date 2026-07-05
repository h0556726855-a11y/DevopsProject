# CI/CD Primer
## What It Is, Why It Exists, How It Works

**Read this before starting the lecture.**
No prior knowledge assumed. Takes ~15 minutes.

---

## The Problem This Solves

Imagine you fixed a bug in `app/backend/app.py`. To get that fix running on a server, you need to:

1. Build the Docker image on your laptop: `docker build -t shoplist-backend:local app/backend/`
2. Save it somewhere: `docker push ...`
3. Tell the server to use the new image: `kubectl apply ...`

Now imagine 5 developers on the same project. Each builds images on their own laptop. Each has slightly different tools, different OS versions, different cached layers. The images they produce are subtly different. Nobody can tell which version is running where.

**CI/CD solves this by removing the human from the process.**

When you push code to Git, a machine automatically builds the image, runs tests, and stores the result. The machine always has the same environment. The output is always reproducible. Every image is traceable back to an exact commit.

---

## The Two Letters

**CI — Continuous Integration**
Every time code is pushed, it is automatically built and tested. Problems are caught immediately, while the change is small and fresh in the developer's mind — not weeks later when ten other changes have stacked on top.

**CD — Continuous Delivery / Continuous Deployment**
After CI passes, the built artifact (a Docker image, in our case) is automatically made available for deployment. In full CD, it is also automatically deployed to an environment. In this course, Lecture 3 covers delivery (images land in the registry automatically). Lecture 4 adds deployment (the cluster updates automatically).

---

## The Four Core Concepts

### 1. Pipeline

A **pipeline** is the sequence of automated steps that runs when you push code. It is defined in a file that lives in your repository — so the pipeline is version-controlled alongside the code it builds.

```
push code → pipeline starts → steps run → result
```

A pipeline either passes (green ✓) or fails (red ✗). If it fails, the image is not pushed. Nobody deploys broken code accidentally.

### 2. Stage

A **stage** is a group of steps within a pipeline. Stages run in order — stage 2 only starts after stage 1 finishes. This lecture has two stages:

```
Stage 1: build   → build and push both images
Stage 2: verify  → confirm both images exist in the registry
```

If `build` fails, `verify` never runs.

### 3. Job

A **job** is a single unit of work inside a stage. Jobs in the same stage run **in parallel** — simultaneously. This lecture's `build` stage has two jobs:

```
build stage:
  build-backend   ──┐
                    ├─ run simultaneously
  build-frontend  ──┘
```

Each job runs in a completely isolated environment — a fresh container. Nothing is shared between jobs by default.

### 4. Runner

A **runner** is the machine that executes jobs. GitLab.com and GitHub provide free shared runners — you do not need to set up any infrastructure. When a pipeline triggers, a runner picks up the job, starts a container, runs your script, and reports the result.

The runner's environment is clean and identical every time. No developer laptop differences. No "it worked on my machine."

---

## The Registry

After building an image, the pipeline pushes it to a **container registry** — a storage service for Docker images.

| Platform | Registry | Image URL format |
|---|---|---|
| GitLab | GitLab Container Registry | `registry.gitlab.com/[group]/[project]/[image]:[tag]` |
| GitHub | GitHub Container Registry (ghcr.io) | `ghcr.io/[owner]/[image]:[tag]` |
| AWS | Elastic Container Registry (ECR) | `[account].dkr.ecr.[region].amazonaws.com/[image]:[tag]` |

The registry is where images live permanently. Kubernetes pulls from the registry when starting pods. The registry is the handoff point between CI (build) and CD (deploy).

---

## Image Tags: The Most Important Detail

Every image in the registry needs a tag — a label that identifies which version it is.

**Wrong: using `:latest`**
```
shoplist-backend:latest   # built Monday
shoplist-backend:latest   # built Wednesday — overwrites Monday silently
```
`:latest` is a mutable tag. It always points to the most recent build. You cannot tell what code is in it. You cannot roll back. Two servers pulling `:latest` at different times get different code.

**Right: using the git commit SHA**
```
shoplist-backend:a1b2c3d4   # Monday's commit — immutable forever
shoplist-backend:e5f6a7b8   # Wednesday's commit — immutable forever
```
A SHA tag is immutable. It always points to exactly one image. You can trace it back to the exact commit, the exact line of code that was changed, and the exact developer who made the change. To roll back: redeploy the previous SHA.

**Rule for this course: images are ALWAYS tagged by SHA. Never `:latest`.**

---

## How GitLab and GitHub Compare

Both platforms provide CI/CD with runners and a container registry. The concepts are identical. The YAML syntax differs.

| Concept | GitLab CI | GitHub Actions |
|---|---|---|
| Pipeline file location | `.gitlab-ci.yml` (project root) | `.github/workflows/*.yml` |
| Trigger keyword | `rules:` / `only:` | `on:` |
| Job definition | top-level key + `stage:` + `script:` | `jobs:` → `steps:` |
| Docker daemon | `services: docker:24-dind` | included in `ubuntu-latest` runners |
| Registry login | `docker login $CI_REGISTRY` | `docker/login-action` with `GITHUB_TOKEN` |
| Commit SHA variable | `$CI_COMMIT_SHORT_SHA` (8 chars, auto) | `${GITHUB_SHA::8}` (slice full SHA in bash) |
| Registry URL | `registry.gitlab.com/[group]/[project]` | `ghcr.io/[owner]` |
| Credentials | `$CI_REGISTRY_USER` / `$CI_REGISTRY_PASSWORD` (auto-injected) | `${{ secrets.GITHUB_TOKEN }}` (auto-injected) |

Neither platform requires you to set up credentials manually — both inject registry tokens automatically into every job.

---

## What a Job Looks Like: Side by Side

**The same job — build and push the backend image — written in both platforms:**

**GitLab CI (`.gitlab-ci.yml`):**
```yaml
build-backend:
  stage: build
  image: docker:24-cli
  services:
    - docker:24-dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $IMAGE_BACKEND:$CI_COMMIT_SHORT_SHA app/backend/
    - docker push $IMAGE_BACKEND:$CI_COMMIT_SHORT_SHA
```

**GitHub Actions (`.github/workflows/build-and-push.yml`):**
```yaml
build-backend:
  runs-on: ubuntu-latest
  permissions:
    packages: write
  steps:
    - uses: actions/checkout@v4
    - name: Set short SHA
      run: echo "SHORT_SHA=${GITHUB_SHA::8}" >> $GITHUB_ENV
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - run: docker build -t ghcr.io/[owner]/shoplist-backend:${{ env.SHORT_SHA }} app/backend/
    - run: docker push ghcr.io/[owner]/shoplist-backend:${{ env.SHORT_SHA }}
```

**What they have in common:**
- Login to registry before pushing
- Build image tagged with commit SHA
- Push to registry
- Clean environment, no manual setup

---

## Vocabulary Reference

| Term | Meaning |
|---|---|
| **Pipeline** | The full sequence of automated steps triggered by a push |
| **Stage** | A group of jobs; stages run in order |
| **Job** | A single unit of work; jobs in the same stage run in parallel |
| **Runner** | The machine that executes jobs |
| **Artifact** | A file produced by a job and passed to later jobs |
| **Registry** | Storage for Docker images |
| **SHA** | A unique identifier for a git commit (e.g. `a1b2c3d4`) |
| **Docker-in-Docker (dind)** | Running a Docker daemon inside a container so CI jobs can build images |
| **`before_script`** (GitLab) | Commands that run before every `script:` in a job — used for login/setup |
| **`steps:`** (GitHub) | The sequential list of commands inside a GitHub Actions job |
| **`rules:`** (GitLab) | Conditions controlling when a job runs |
| **`on:`** (GitHub) | Events that trigger a workflow |
| **`needs:`** (both) | Declares that a job depends on another job completing first |

---

## How This Fits the Course

| Lecture | What You Do | Manual Steps |
|---|---|---|
| L1 — Docker | `docker build`, `docker compose up` | Everything |
| L2 — Kubernetes | `kubectl apply`, `k3d image import` | Everything |
| **L3 — CI/CD** | `git push` — pipeline does the rest | Update manifest with new SHA |
| L4 — Cloud | `git push` — pipeline builds AND deploys | Nothing |

Each lecture removes one more manual step. By Lecture 4, a single `git push` takes code all the way to a running pod in a cloud cluster.

---

## Before You Start the Lab

Make sure you can answer these:

1. What is the difference between a stage and a job?
2. Why does build-backend and build-frontend run at the same time?
3. What happens if build-backend fails — does verify-registry still run?
4. Why do we tag images with a SHA and not `:latest`?
5. What is a runner?

If any of these are unclear, re-read the relevant section above before opening `.gitlab-ci.yml` or the GitHub Actions file.
