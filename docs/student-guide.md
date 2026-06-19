# Lecture 1 — Docker & Docker Compose
## Student Guide

---

## Lecture Outcome (STRICT)

**What exists at the end of this lecture:**

| File | Purpose |
|------|---------|
| `app/backend/app.py` | Flask REST API |
| `app/backend/requirements.txt` | Python dependencies |
| `app/backend/Dockerfile` | Backend container definition |
| `app/frontend/index.html` | UI markup |
| `app/frontend/app.js` | UI logic |
| `app/frontend/style.css` | UI styling |
| `app/frontend/nginx.conf` | Nginx configuration with proxy |
| `app/frontend/Dockerfile` | Frontend container definition |
| `docker/docker-compose.yml` | Multi-container orchestration |
| `docker/init.sql` | Database initialization |

**What does NOT exist yet:**
- No Kubernetes manifests
- No GitLab CI/CD pipeline
- No Terraform files
- No Ansible files
- No cloud infrastructure of any kind

**What you CAN do after this lecture:**
- Run the full application locally with one command
- Add, view, and delete products in the browser
- Explain every file and every line you wrote

**What you CANNOT do yet:**
- Deploy to any server
- Run on Kubernetes
- Automate builds

---

## What You Will Build

A 3-container web application running on your local machine.

```
Browser → Frontend (Nginx :80) → Backend (Flask :5000) → Database (PostgreSQL :5432)
```

By the end of this lecture you will type one command and have a working web application running entirely inside containers on your machine.

---

## What You Will Learn

- What a container is and why it replaced VMs for application deployment
- How to write a Dockerfile for a Python application
- How to write a Dockerfile for an Nginx web server
- How Nginx can act as a reverse proxy to route requests
- How Docker Compose connects multiple containers into one system
- How named volumes make database data persist across restarts

---

## Prerequisites

Before starting, verify every item:

- [ ] WSL2 with Ubuntu 22.04 is installed and opens without error
- [ ] Docker Desktop is installed, running, and WSL2 integration is enabled
- [ ] You can run `docker --version` inside WSL2 and see a version number
- [ ] You can run `docker compose version` inside WSL2 and see a version number
- [ ] VS Code with Remote WSL extension is installed
- [ ] The project repo is cloned and you are on branch `feature/lecture-1`

If any item fails, stop and resolve it before continuing.

---

## Part 1 — Core Concepts

Read this section before writing any files. Understanding why before how is the difference between following instructions and actually learning.

---

### Concept: Container

**What it is:**
A container is a lightweight, isolated process that packages an application together with everything it needs to run — code, runtime, libraries, and configuration — in one portable unit.

**Why it exists:**
Before containers, deploying an application meant manually installing the correct Python version, the correct library versions, and the correct system dependencies on every server. If the server had a different version of anything, the app might fail in unpredictable ways. This was so common it had a name: "works on my machine." Containers eliminate this by shipping the environment alongside the code.

**How it works:**
Docker uses Linux kernel features (namespaces and cgroups) to create an isolated process. The container sees only its own filesystem, network, and processes. It shares the host machine's kernel but cannot see or interfere with other containers unless you explicitly configure it to. The result is an isolated environment that behaves identically on any machine that runs Docker.

**Common mistake:**
Confusing an image with a container. An **image** is a static, read-only snapshot — like a template or a class in programming. A **container** is a running instance of that image — like an object. You can run 10 containers from the same image simultaneously. When you stop a container, the image still exists unchanged.

---

### Concept: Dockerfile

**What it is:**
A plain text file containing ordered instructions that tell Docker how to build an image.

**Why it exists:**
Without a Dockerfile, building an image would require running manual commands every time. A Dockerfile makes image creation repeatable, automated, and version-controlled. Anyone with the Dockerfile can build the exact same image.

**How it works:**
Docker reads the Dockerfile top to bottom and executes each instruction. Each instruction creates a new read-only **layer** on top of the previous one. Docker caches these layers — if a layer's instruction has not changed, Docker reuses the cached result instead of re-executing it. The final stack of layers is the image.

Key instructions:

| Instruction | What it does |
|-------------|-------------|
| `FROM` | Sets the base image to start from |
| `WORKDIR` | Sets the working directory for all subsequent instructions |
| `COPY` | Copies files from host into the image |
| `RUN` | Executes a shell command during the build |
| `EXPOSE` | Documents which port the application uses |
| `CMD` | Sets the default command to run when the container starts |

**Common mistake:**
Putting `COPY . .` before `RUN pip install`. When you copy all files first, Docker creates a new cache key for the install layer every time any file changes — including files that have nothing to do with dependencies. The correct order is: copy `requirements.txt` first, install dependencies (this layer is now cached), then copy the rest of the application. Dependency installation only re-runs when `requirements.txt` changes.

---

### Concept: Docker Compose

**What it is:**
A tool for defining and running multi-container applications using a single YAML file (`docker-compose.yml`).

**Why it exists:**
Our application has three containers: frontend, backend, and database. Without Compose, you would start each container with a separate `docker run` command that includes all ports, environment variables, network settings, and volume mounts. Compose defines the entire system in one file and starts everything with one command: `docker compose up`.

**How it works:**
The `docker-compose.yml` file defines a list of **services**. Each service describes one container. Compose automatically creates a shared network and adds all services to it. Services discover each other using the **service name as the hostname** — no IP addresses needed. If one service is named `postgres`, other containers reach it at `postgres:5432`.

**Common mistake:**
Assuming `depends_on` waits for a service to be fully ready. By default, `depends_on` only waits until the dependent container's process has started — not until the application inside it is ready to accept connections. A PostgreSQL container can be "started" but still initializing its data directory. The correct pattern is to combine `depends_on` with a `healthcheck` and `condition: service_healthy`.

---

### Concept: Docker Volume

**What it is:**
A mechanism for persisting data outside a container's temporary filesystem.

**Why it exists:**
A container's filesystem is ephemeral — when the container is removed, all data written inside it is gone. For a database, this would mean losing all records every time you restart. Volumes solve this by storing data on the host machine and mounting it into the container at a specific path. The container reads and writes to that path as if it were local, but the data lives on the host.

**How it works:**
You declare a **named volume** in `docker-compose.yml`. Docker creates and manages the storage location on the host. You mount the volume to the path where the database stores its files (for PostgreSQL: `/var/lib/postgresql/data`). When the container restarts, Docker mounts the same volume and the database finds all its data intact.

**Common mistake:**
Running `docker compose down -v`. The `-v` flag deletes all named volumes. Without `-v`, `docker compose down` preserves volumes and your data survives. This distinction matters enormously in production — `down -v` is a destructive operation.

---

## Part 2 — Step-by-Step Instructions

Write and verify each step before moving to the next.

---

### Step 1 — Create the database initialization script

PostgreSQL automatically executes any `.sql` files placed in `/docker-entrypoint-initdb.d/` on first startup. You will use this to create the `products` table.

Create `docker/init.sql`:

```sql
CREATE TABLE IF NOT EXISTS products (
    id     SERIAL PRIMARY KEY,
    name   VARCHAR(100) NOT NULL,
    price  NUMERIC(10, 2) NOT NULL
);
```

**What each line does:**
- `CREATE TABLE IF NOT EXISTS` — safe to run multiple times; does nothing if the table already exists
- `id SERIAL PRIMARY KEY` — auto-incrementing integer, unique identifier for each product
- `name VARCHAR(100) NOT NULL` — text up to 100 characters, cannot be empty
- `price NUMERIC(10, 2) NOT NULL` — decimal number with 2 decimal places, cannot be empty

---

### Step 2 — Write the backend application

Create `app/backend/requirements.txt`:

```
flask==3.0.3
psycopg2-binary==2.9.9
```

These are the only two libraries the backend needs. Flask is the web framework. psycopg2-binary is the PostgreSQL driver for Python.

Create `app/backend/app.py`:

```python
from flask import Flask, jsonify, request
import psycopg2
import os

app = Flask(__name__)


def get_db():
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/products', methods=['GET'])
def get_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, name, price FROM products ORDER BY id')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{'id': r[0], 'name': r[1], 'price': float(r[2])} for r in rows])


@app.route('/products', methods=['POST'])
def add_product():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO products (name, price) VALUES (%s, %s) RETURNING id',
        (data['name'], data['price'])
    )
    product_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': product_id, 'name': data['name'], 'price': data['price']}), 201


@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    cur.close()
    conn.close()
    return '', 204


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

**Key observations:**
- Database credentials come from environment variables (`os.environ`). They are never written in the code.
- `get_db()` opens a new connection per request. Simple and sufficient for a learning project.
- `/health` requires no database — it exists only to let Docker verify the container is alive.
- `host='0.0.0.0'` — Flask must listen on all interfaces inside a container, not just localhost.

---

### Step 3 — Write the backend Dockerfile

Create `app/backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]
```

**Line by line:**
- `FROM python:3.11-slim` — official Python image, `slim` variant reduces image size by removing non-essential packages
- `WORKDIR /app` — creates and sets `/app` as the working directory inside the container
- `COPY requirements.txt .` — copies only the requirements file first (layer caching)
- `RUN pip install --no-cache-dir -r requirements.txt` — installs dependencies; cached until requirements.txt changes
- `COPY app.py .` — copies application code in a separate layer
- `EXPOSE 5000` — documentation only; does not publish the port
- `CMD ["python", "app.py"]` — default command when the container starts

Test the build in isolation:

```bash
cd app/backend
docker build -t shoplist-backend:local .
```

Expected: build completes with no errors. You will see each layer execute.

---

### Step 4 — Write the Nginx configuration

Nginx will serve the HTML/JS files and proxy API calls to the backend. The browser never talks to the backend directly.

Create `app/frontend/nginx.conf`:

```nginx
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:5000/;
        proxy_set_header Host $host;
    }
}
```

**How routing works:**
- Browser requests `/` or any static file → Nginx serves from `/usr/share/nginx/html`
- Browser requests `/api/products` → Nginx strips `/api/` and forwards to `http://backend:5000/products`
- `backend` is the Docker Compose service name — Compose resolves it to the backend container's IP automatically

This pattern is called a **reverse proxy**. The browser only ever talks to Nginx. The backend is not accessible directly from outside the Docker network.

---

### Step 5 — Write the frontend files

Create `app/frontend/style.css`:

```css
body { font-family: sans-serif; max-width: 600px; margin: 2rem auto; padding: 0 1rem; }
h1 { color: #1e293b; }
form { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
input { padding: 0.4rem 0.6rem; border: 1px solid #cbd5e1; border-radius: 4px; flex: 1; }
button { padding: 0.4rem 0.85rem; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
button:hover { background: #1d4ed8; }
ul { list-style: none; padding: 0; }
li { display: flex; justify-content: space-between; align-items: center; padding: 0.65rem 0; border-bottom: 1px solid #e2e8f0; }
li button { background: #dc2626; font-size: 0.8rem; }
```

Create `app/frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ShopList</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>ShopList</h1>
  <form id="add-form">
    <input type="text" id="name" placeholder="Product name" required>
    <input type="number" id="price" placeholder="Price" step="0.01" min="0" required>
    <button type="submit">Add Product</button>
  </form>
  <ul id="product-list"></ul>
  <script src="app.js"></script>
</body>
</html>
```

Create `app/frontend/app.js`:

```javascript
const API = '/api';

async function loadProducts() {
  const response = await fetch(`${API}/products`);
  const products = await response.json();
  const list = document.getElementById('product-list');
  list.innerHTML = products.map(p =>
    `<li>
      <span>${p.name} — $${parseFloat(p.price).toFixed(2)}</span>
      <button onclick="deleteProduct(${p.id})">Delete</button>
    </li>`
  ).join('');
}

async function deleteProduct(id) {
  await fetch(`${API}/products/${id}`, { method: 'DELETE' });
  loadProducts();
}

document.getElementById('add-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('name').value.trim();
  const price = parseFloat(document.getElementById('price').value);
  await fetch(`${API}/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, price })
  });
  e.target.reset();
  loadProducts();
});

loadProducts();
```

**Notice:** `API = '/api'` uses a relative path. The browser sends all requests to the same Nginx server that served the HTML. Nginx handles routing to the backend internally.

---

### Step 6 — Write the frontend Dockerfile

Create `app/frontend/Dockerfile`:

```dockerfile
FROM nginx:1.25-alpine

COPY index.html  /usr/share/nginx/html/
COPY app.js      /usr/share/nginx/html/
COPY style.css   /usr/share/nginx/html/
COPY nginx.conf  /etc/nginx/conf.d/default.conf

EXPOSE 80
```

**Note:** This Dockerfile copies the custom `nginx.conf` over the default Nginx configuration. The `EXPOSE 80` is documentation only.

---

### Step 7 — Write Docker Compose

Create `docker/docker-compose.yml`:

```yaml
services:

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: shoplist
      POSTGRES_USER: shopuser
      POSTGRES_PASSWORD: shoppass
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U shopuser -d shoplist"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ../app/backend
    environment:
      DB_HOST: postgres
      DB_NAME: shoplist
      DB_USER: shopuser
      DB_PASSWORD: shoppass
    depends_on:
      postgres:
        condition: service_healthy

  frontend:
    build:
      context: ../app/frontend
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  postgres-data:
```

**Key decisions:**
- `postgres:15-alpine` — minimal Alpine-based image, smaller and faster to pull
- `POSTGRES_DB/USER/PASSWORD` — these environment variables are read by the postgres image on first startup to initialize the database
- `./init.sql:/docker-entrypoint-initdb.d/init.sql` — mounts the SQL file so postgres runs it on first launch only
- `healthcheck` — postgres is marked healthy only when `pg_isready` succeeds (actually accepting connections)
- `condition: service_healthy` — backend container waits for postgres to be healthy before starting
- Backend has no `ports:` — it is only reachable within the Docker network, not from your host machine
- Frontend exposes port `80:80` — this is the only service the browser talks to directly

---

### Step 8 — Run and verify

```bash
cd docker
docker compose up --build
```

Wait for all three services to show as running. Expected output (excerpt):

```
postgres-1  | database system is ready to accept connections
backend-1   | * Running on all addresses (0.0.0.0)
backend-1   | * Running on http://127.0.0.1:5000
frontend-1  | /docker-entrypoint.sh: Configuration complete; ready for start up
```

Open `http://localhost` in your browser. Add two products. Verify they appear in the list.

---

### Step 9 — Verify persistence

```bash
# Stop all containers (volumes preserved)
docker compose down

# Start again
docker compose up

# Open http://localhost — products are still there
```

Now see what data loss looks like:

```bash
docker compose down -v    # -v deletes volumes
docker compose up --build
# Open http://localhost — products are gone
```

Remember this. The `-v` flag is destructive.

---

## Interview Questions

**Q: What is the difference between a Docker image and a container?**
A: An image is a read-only template — a static snapshot of a filesystem with the application and all its dependencies. A container is a running instance of an image. The image does not change when you run or stop a container. You can create many containers from the same image.

**Q: What does EXPOSE do in a Dockerfile?**
A: EXPOSE is documentation. It records which port the application listens on so that developers and tools know where to connect. It does not actually publish or open the port. Publishing happens in docker-compose.yml under `ports`, or with the `-p` flag in `docker run`.

**Q: Why does the order of instructions in a Dockerfile matter?**
A: Because Docker caches each layer. If you change a file, Docker invalidates the cache for that layer and all layers after it. By copying `requirements.txt` before the application code and installing dependencies immediately after, you ensure the slow install step is cached and only re-runs when dependencies actually change.

**Q: How do containers in Docker Compose communicate?**
A: Compose creates a shared network and adds all services to it. Each service is reachable from other services using the service name as the hostname. No IP addresses or port configuration needed between services — only ports exposed to the host need the `ports:` mapping.

**Q: What is the difference between `docker compose down` and `docker compose down -v`?**
A: `docker compose down` stops containers and removes the network but preserves named volumes. `docker compose down -v` also deletes named volumes, permanently destroying any data stored in them. For a database, this means all records are gone.
