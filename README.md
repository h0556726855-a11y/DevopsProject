# DevOps Final Project 2026

## Overview
This project demonstrates a complete containerized web application using Docker, Docker Compose and Kubernetes.

## Project Structure

```
app/
  backend/      Flask REST API
  frontend/     HTML/CSS/JavaScript application
docker/
  docker-compose.yml
  init.sql
kubernetes/
  Kubernetes manifests
docs/
  Course documentation
```

## Technologies
- Python (Flask)
- PostgreSQL
- HTML, CSS, JavaScript
- Docker
- Docker Compose
- Kubernetes
- Nginx

## Features
- REST API for product management
- PostgreSQL database
- Frontend interface
- Health endpoint
- Dockerized services
- Kubernetes deployment manifests

## Run with Docker Compose

```bash
cd docker
docker compose up --build
```

## Kubernetes

```bash
kubectl apply -f kubernetes/
```

## API Endpoints

- GET /health
- GET /products
- POST /products
- DELETE /products/{id}

## Author

HODAYA ILYABAYEV
