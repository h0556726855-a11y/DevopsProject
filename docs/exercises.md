# Lecture 1 — Exercises
## Docker & Docker Compose

---

**Instructions:**
- Complete exercises in order
- Do not look at the student guide unless you are stuck
- Verify each exercise before moving to the next
- Work on branch `feature/lecture-1`

---

## Exercise 1 — Inspect a Running Container (Easy)

**Task:**
Start the application with `docker compose up --build` (from the `docker/` directory).
Without stopping it, open a second terminal and answer these questions using only `docker` commands:

1. List all running containers and identify their names
2. View the live logs of the backend container only
3. Find out which environment variables are set inside the backend container
4. Find the IP address Docker assigned to the backend container

**Commands to research:**
`docker ps`, `docker logs`, `docker inspect`, `docker exec`

**Expected results:**
1. Three containers running: postgres, backend, frontend
2. Backend logs show Flask startup messages
3. Environment variables include `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
4. An IP address in the `172.x.x.x` range

**Validation command:**
```bash
docker inspect $(docker ps -qf "name=backend") --format '{{.NetworkSettings.Networks}}'
```

---

## Exercise 2 — Break and Fix the Dockerfile (Medium)

**Task:**
Make the following deliberate mistake in `app/backend/Dockerfile`:

Move the line `COPY requirements.txt .` to AFTER the line `COPY app.py .`

Then:
1. Build the image: `docker build -t shoplist-backend:broken .` — note the build time
2. Change one line in `app.py` (e.g. add a space somewhere)
3. Build again: `docker build -t shoplist-backend:broken .` — observe what happens to the pip install step

Then fix the Dockerfile back to the correct order and observe the difference.

**What you are observing:**
- With wrong order: pip install re-runs every time any file changes
- With correct order: pip install is cached and skipped unless requirements.txt changes

**Expected result:**
Broken order — pip install runs on every build even for trivial code changes.
Correct order — pip install shows `CACHED` on the second build.

**Validation:**
```bash
docker build -t shoplist-backend:fixed . 2>&1 | grep -E "CACHED|pip install"
```
You should see `CACHED` next to the pip install step.

---

## Exercise 3 — Remove the Healthcheck and Observe the Result (Medium)

**Task:**
In `docker/docker-compose.yml`, remove the entire `healthcheck:` block from the postgres service.
Also change `condition: service_healthy` to `condition: service_started` on the backend's `depends_on`.

Stop everything with `docker compose down`, then start again with `docker compose up --build`.

**Observe:**
- Does the backend start correctly?
- Check `docker compose logs backend` for any connection errors
- How many times does the backend fail before postgres is ready?

Then restore the healthcheck to the original configuration.

**What you are learning:**
`depends_on: condition: service_healthy` is not a convenience — it is a correctness guarantee. Without it, the startup order is a race condition.

**Expected result:**
Without healthcheck: backend likely logs connection errors before successfully connecting.
With healthcheck: backend starts cleanly with no connection errors.

**Validation:**
```bash
docker compose logs backend | grep -i "error\|ready\|running"
```

---

## Bonus Exercise — Custom Error Response (Optional)

**Task:**
Add a new route to `app/backend/app.py`:

```
GET /products/<id>   →   returns a single product as JSON
                     →   returns 404 with {"error": "not found"} if the product does not exist
```

Rebuild the backend image, restart the stack, and test your new endpoint with:

```bash
curl http://localhost/api/products/1      # should return the product
curl http://localhost/api/products/9999   # should return 404
```

**This exercise is not required to pass the lecture.**
It is for students who finish early and want to deepen their Flask knowledge.
