# Lecture 3 — GitLab CI/CD
## Exercises

---

## Exercise 1 — Inspect the Pipeline (Easy)

**Type:** Observation  
**Duration:** ~10 minutes  
**Goal:** Read and understand the full `.gitlab-ci.yml` without changing anything.

---

### Task

Open `.gitlab-ci.yml` at the project root and answer the following questions in writing or aloud.

**Question 1:** How many jobs are defined? List them by name.

**Question 2:** Which stage does each job belong to?

**Question 3:** Two jobs run in parallel. Which two, and why do they run in parallel?

**Question 4:** The `push-images` job has an `only:` block. What does it restrict, and what is the expected behavior when you push to `feature/lecture-3`?

**Question 5:** Every job includes these two lines:
```yaml
image: docker:24
services:
  - docker:24-dind
```
What would happen to the job if you removed the `services:` block? Which specific command would fail first?

**Question 6:** The `test-backend` job rebuilds the backend image with `docker build` even though `build-backend` already built it. Why?

**Question 7:** What is `$CI_COMMIT_SHORT_SHA`, and what value would it have if your latest git commit hash is `abc123456789`?

---

### Expected answers

**Q1:** 4 jobs: `build-backend`, `build-frontend`, `test-backend`, `push-images`.

**Q2:** `build-backend` → build. `build-frontend` → build. `test-backend` → test. `push-images` → push.

**Q3:** `build-backend` and `build-frontend` both belong to the `build` stage. Jobs within the same stage run in parallel.

**Q4:** `only: dev, main` means `push-images` runs only when the trigger branch is `dev` or `main`. On `feature/lecture-3`, this job is skipped. Build and test still run.

**Q5:** Removing `services: - docker:24-dind` removes the Docker daemon. The first `docker build` command fails with `Cannot connect to the Docker daemon at unix:///var/run/docker.sock.`

**Q6:** Each job runs in a fresh, isolated container. The image built in `build-backend` is not available to `test-backend` — they run in separate containers with separate Docker daemons. The rebuild is required.

**Q7:** `$CI_COMMIT_SHORT_SHA` is a GitLab predefined CI variable containing the first 8 characters of the commit hash. For hash `abc123456789`, the value would be `abc12345`.

---

## Exercise 2 — Remove dind and Observe Failure (Medium)

**Type:** Break-and-fix  
**Duration:** ~15 minutes  
**Goal:** Experience the exact Docker daemon failure, then restore the working state.

---

### Part A — Introduce the break

Edit `.gitlab-ci.yml`. In the `test-backend` job, remove the `services:` block:

**Before:**
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

**After (broken):**
```yaml
test-backend:
  stage: test
  image: docker:24
  script:
    - docker build -t $BACKEND_IMAGE:$IMAGE_TAG app/backend/
    - docker run --rm $BACKEND_IMAGE:$IMAGE_TAG python -c "from flask import Flask; import psycopg2; print('All dependencies OK')"
```

Push to your feature branch:
```bash
git add .gitlab-ci.yml
git commit -m "exercise: remove dind from test-backend"
git push origin feature/lecture-3
```

---

### Part B — Observe and record the failure

Open GitLab → CI/CD → Pipelines. Watch the new pipeline.

Answer these questions:

1. Which stage fails?
2. Which specific jobs pass or fail?
3. Open the `test-backend` job log. What is the exact error message on the first failing line?
4. Does `push-images` run? Why or why not?

**Expected observations:**
- `build-backend` and `build-frontend`: pass
- `test-backend`: **fail** — error message: `Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?`
- `push-images`: **does not run** — the test stage failed, so the push stage is cancelled

The pipeline stops at the first failure. This is the safety property: a broken test prevents a broken image from reaching the registry.

---

### Part C — Restore the fix

Restore the `services:` block to `test-backend`:
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

```bash
git add .gitlab-ci.yml
git commit -m "exercise: restore dind in test-backend"
git push origin feature/lecture-3
```

Verify the pipeline passes all 3 stages (push is still skipped on the feature branch — this is correct).

---

## Exercise 3 — Change to :latest Tag and Observe Registry (Medium)

**Type:** Remove-and-observe  
**Duration:** ~15 minutes  
**Goal:** Understand why SHA tagging exists by experiencing the :latest problem firsthand.

---

### Part A — Switch to :latest

Edit `.gitlab-ci.yml`. Change the `IMAGE_TAG` variable:

**Before:**
```yaml
variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
  FRONTEND_IMAGE: $CI_REGISTRY_IMAGE/frontend
  IMAGE_TAG: $CI_COMMIT_SHORT_SHA
```

**After (modified):**
```yaml
variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
  FRONTEND_IMAGE: $CI_REGISTRY_IMAGE/frontend
  IMAGE_TAG: latest
```

Commit and push to `dev` to trigger a full pipeline including push:

```bash
git add .gitlab-ci.yml
git commit -m "exercise: switch to :latest tag"
git push origin dev
```

Wait for the pipeline to complete (all 4 jobs including `push-images`).

---

### Part B — Observe the registry

Open GitLab → Deploy → Container Registry → backend.

Answer these questions:

1. How many tags are listed?
2. What is the tag name?
3. From the tag name alone, can you tell which git commit built this image?
4. Make one more commit and push to dev. Now how many tags are listed?

**Expected observations:**
- After first push: 1 tag named `latest`
- After second push: still 1 tag named `latest` — the previous image was overwritten
- From the tag `latest`, you cannot determine which commit built the image
- If the second push introduced a bug, you cannot easily pull the previous version — you would need to re-run the earlier commit's pipeline

This is the `:latest` problem. Every push overwrites the pointer. History is lost.

---

### Part C — Restore SHA tagging

Revert the `IMAGE_TAG` variable:
```yaml
variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
  FRONTEND_IMAGE: $CI_REGISTRY_IMAGE/frontend
  IMAGE_TAG: $CI_COMMIT_SHORT_SHA
```

```bash
git add .gitlab-ci.yml
git commit -m "exercise: restore SHA tagging"
git push origin dev
```

After the pipeline completes, check the registry again. You should now see a tag that matches:
```bash
git log --oneline -1
# The 8-character prefix is your image tag
```

---

## Bonus Exercise — Add a yamllint Validation Stage (Optional)

**Type:** Extension  
**Duration:** ~20 minutes  
**Goal:** Add a linting stage that validates `.gitlab-ci.yml` syntax before the build stage runs.

---

### Background

`yamllint` is a Python tool that checks YAML files for syntax errors, indentation problems, and style violations. Adding it as a pre-build stage catches broken YAML before it wastes runner time on a build that would fail for a different reason.

---

### Task

Add a new `validate` stage that runs before `build`. Add a `lint-yaml` job that uses the `python:3.11-slim` image and runs `yamllint` on `.gitlab-ci.yml`.

Update the `stages` list:
```yaml
stages:
  - validate
  - build
  - test
  - push
```

Add the lint job:
```yaml
lint-yaml:
  stage: validate
  image: python:3.11-slim
  script:
    - pip install yamllint --quiet
    - yamllint .gitlab-ci.yml
```

No `services:` is needed — this job does not use Docker.

Push to the feature branch:
```bash
git add .gitlab-ci.yml
git commit -m "ci: add yamllint validation stage"
git push origin feature/lecture-3
```

---

### What to verify

1. The pipeline now has 4 stages: validate, build, test, push
2. `lint-yaml` runs first and passes
3. Introduce a deliberate YAML indentation error. Observe that `lint-yaml` fails and the build stage is cancelled

**To introduce a deliberate error:** remove two spaces of indentation from any `script:` line so it aligns incorrectly. Push and observe the lint failure. Restore the correct indentation to make lint pass again.

---

### Expected pipeline on feature branch with bonus:
- `lint-yaml` → passed (validate stage)
- `build-backend` + `build-frontend` → passed (build stage)
- `test-backend` → passed (test stage)
- `push-images` → skipped (push stage — feature branch only)
