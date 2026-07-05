# Cloud Primer
## What It Is, Why It Exists, How It Works

**Read this before starting the lecture.**
No prior cloud knowledge assumed. Takes ~15 minutes.

---

> **Read this before the lecture.**
> This primer gives you the vocabulary and mental model you need before touching any AWS console or Terraform file. The lab moves fast. Students who skip this spend most of their time confused by terminology rather than learning the concepts.
> If something is unclear after reading, re-read that section — do not skip ahead.

---

## The Problem This Solves

By the end of Lecture 3, your pipeline automatically builds a Docker image and pushes it to a registry every time you run `git push`. That is a real improvement. But something is still missing.

**The image is in the registry. Nobody is running it.**

To actually serve traffic, someone still has to:

1. SSH into a server
2. Run `kubectl apply -f ...` manually
3. Hope the server is still running and reachable

This breaks in three ways:
- If the server goes down, the app goes down too
- The server only has a private IP — nobody outside your network can reach it
- There is no automation: a human must act every time

**Cloud solves this.** AWS gives you rented computers that are always on, have a public IP address, and can be managed entirely through code. Combined with Terraform and EKS, a `git push` can take code all the way from your laptop to a running pod reachable anywhere in the world — with no manual steps.

---

## What is AWS?

**Amazon Web Services** is the largest cloud provider in the world. "Cloud" means you rent computing resources — servers, storage, networks — by the hour, instead of buying and maintaining physical hardware.

### Regions

A **region** is a physical location where AWS operates data centers. You choose a region when you create resources.

| Region code | Location |
|---|---|
| `eu-west-1` | Ireland |
| `us-east-1` | Northern Virginia |
| `us-west-2` | Oregon |
| `ap-southeast-1` | Singapore |

Resources in one region are completely separate from another. This lab uses `eu-west-1` by default — close to Israel, low latency.

### Availability Zones

Inside each region, AWS has multiple **Availability Zones (AZs)** — physically separate buildings with independent power, cooling, and networking. If one building catches fire, the others keep running.

A region typically has 3 AZs. `eu-west-1` has `eu-west-1a`, `eu-west-1b`, `eu-west-1c`.

**Rule of thumb:** Region = country/city. AZ = a specific building in that city.

### Pay-per-hour

AWS charges by the hour (or second) for most resources. **Costs stop when you delete the resource.** A cluster running overnight = wasted money. This is why `terraform destroy` is not optional — it is mandatory at the end of the lab.

---

## What is a VPC?

A **Virtual Private Cloud (VPC)** is your own private network inside AWS. Think of it as a fenced-off area of the internet that only you control.

Without a VPC, every resource you create would be directly exposed to the internet with no isolation. The VPC is the boundary.

### Subnets

Inside a VPC, you divide the address space into **subnets**.

| Subnet type | Reachable from internet? | Use case |
|---|---|---|
| **Public subnet** | Yes, directly | Load balancers, bastion hosts |
| **Private subnet** | No — needs NAT gateway | Databases, worker nodes |

A **NAT gateway** lets resources in a private subnet reach the internet (for downloading packages) without being reachable from outside. It costs ~$0.045/hour, which adds up.

**This lab uses public subnets only.** Worker nodes sit in public subnets. This is simpler and avoids the NAT gateway charge. It is not recommended for production, but it is fine for a learning lab.

---

## What is Terraform?

**Terraform** is Infrastructure as Code (IaC). Instead of clicking through the AWS console to create resources, you write `.tf` files that describe what you want. Terraform reads those files and creates, updates, or deletes AWS resources to match.

### Why this matters

If you click through the console to create a cluster:
- Nobody knows what you clicked
- You cannot reproduce it exactly
- You cannot delete everything cleanly
- There is no history, no review, no audit trail

If you write Terraform files:
- The infrastructure is version-controlled alongside the application code
- Anyone can read exactly what exists and why
- `terraform destroy` deletes everything you created, cleanly
- You can create an identical environment from scratch in minutes

### The four commands you will use

| Command | What it does |
|---|---|
| `terraform init` | Downloads the provider plugins (AWS, etc.) — run once per project |
| `terraform plan` | Shows what Terraform *would* create/change/delete — no changes are made |
| `terraform apply` | Actually creates or updates resources in AWS |
| `terraform destroy` | Deletes all resources Terraform created — **run this at the end of the lab** |

**Always run `terraform plan` before `terraform apply`.** Read the output. Confirm that what Terraform plans to create matches what you expect. Apply without planning is how unexpected charges happen.

### The state file

Terraform tracks what it has created in a file called `terraform.tfstate`. This is how it knows what to update or delete.

**Never delete or manually edit `terraform.tfstate`.** If you lose it, Terraform loses track of your resources — they keep running and charging you, but Terraform cannot manage them.

### Why modules?

A **module** is pre-written Terraform code that you can reuse. This lab uses two community modules:

- `terraform-aws-modules/vpc` — creates a complete VPC with subnets, routing tables, internet gateway
- `terraform-aws-modules/eks` — creates a complete EKS cluster with node groups

Without these modules, creating an EKS cluster correctly requires 20+ individual resource blocks — security groups, IAM roles, launch templates, autoscaling groups, and more. With the modules, it takes two blocks. The modules encode best practices so you do not have to learn all of them before you can do anything useful.

```hcl
# Without modules: 20+ blocks, hundreds of lines
# With modules: 2 blocks

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"
  # ...
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.0.0"
  # ...
}
```

---

## What is EKS?

**Elastic Kubernetes Service (EKS)** is AWS's managed Kubernetes offering. You already know Kubernetes from Lecture 2. EKS is the same Kubernetes — the same `kubectl`, the same manifests, the same concepts — running on AWS infrastructure.

### What "managed" means

Kubernetes has two layers:

| Layer | What it includes | Who manages it on EKS |
|---|---|---|
| **Control plane** | API server, etcd, scheduler, controller manager | AWS |
| **Data plane** | Worker nodes (EC2 instances running your pods) | You |

AWS keeps the control plane running, updated, and highly available. You never SSH into an API server or worry about etcd backups. You only manage the worker nodes — and even those can be managed automatically with node groups.

### Node groups

A **node group** is a set of identical EC2 instances that serve as Kubernetes worker nodes. You define the instance type and min/max count. AWS handles launching, replacing failed nodes, and scaling.

This lab uses **t3.micro** instances for worker nodes.

| Instance type | vCPU | RAM | Free tier? |
|---|---|---|---|
| `t3.micro` | 2 | 1 GB | Yes — 750 hours/month |
| `t3.small` | 2 | 2 GB | No |
| `t3.medium` | 2 | 4 GB | No |

`t3.micro` is sufficient for this lab. The control plane is not free-tier eligible — see the cost section below.

---

## What Changes in Kubernetes for Cloud?

The manifests from Lecture 2 mostly carry over unchanged. Two things work differently on EKS.

### Services: NodePort vs LoadBalancer

On your local cluster (k3d), you used `NodePort` services and accessed the app at `localhost:30080`.

On EKS, you use `LoadBalancer` services instead.

| Service type | Where you used it | How you access the app |
|---|---|---|
| `NodePort` | Lecture 2, local cluster | `localhost:30080` |
| `LoadBalancer` | Lecture 4, EKS | AWS DNS name, port 80 |

When Kubernetes sees a `LoadBalancer` service on EKS, it automatically tells AWS to create an **Elastic Load Balancer (ELB)**. AWS creates the load balancer, assigns it a public DNS name, and routes traffic from port 80 to your pods. You do not configure this manually — changing `type: NodePort` to `type: LoadBalancer` is the entire change.

```yaml
# Lecture 2 — local
spec:
  type: NodePort
  ports:
    - port: 80
      nodePort: 30080

# Lecture 4 — EKS
spec:
  type: LoadBalancer
  ports:
    - port: 80
```

### Persistent Volumes: hostPath vs EBS

On a local cluster, `PersistentVolumeClaims` used `hostPath` — a directory on the local machine.

On EKS, the default storage class (`gp2`) automatically provisions **Elastic Block Storage (EBS)** volumes. Your PVC manifests do not need to change — just remove any explicit `storageClassName: hostpath`. EKS handles the rest.

---

## Cost Warning

EKS is not fully free. Running a lab cluster for 3 hours costs approximately **$0.40**. Leaving it running overnight costs approximately **$3**. Leaving it running for a week = ~$21 for something producing nothing.

| Resource | Cost | Notes |
|---|---|---|
| EKS control plane | $0.10/hr | The only non-free item — cannot be avoided |
| t3.micro worker node | Free (free tier) | 750 hrs/month free per account |
| EBS 1Gi volume | ~$0.001/day | Negligible |
| Classic ELB (load balancer) | ~$0.025/hr | Only while lab is running |
| **Estimated 3-hour lab total** | **~$0.40** | Assuming free-tier account |

### ALWAYS run terraform destroy when done

```bash
terraform destroy
```

This deletes the EKS cluster, node group, load balancer, VPC, and all associated resources. It takes about 10 minutes. Wait for it to finish — partial deletion still incurs charges.

### Verify deletion in the AWS Console

After `terraform destroy` completes, confirm in the AWS Console:

1. **EKS** — no clusters listed
2. **EC2 > Instances** — no instances in running state
3. **EC2 > Load Balancers** — no load balancers listed
4. **VPC** — only the default VPC (the one that exists before you do anything)

If anything is still there, delete it manually. A forgotten load balancer costs $18/month.

---

## How This Fits the Course

Each lecture removes one more manual step. By the end of Lecture 4, the only action you take is `git push`. Everything else is automated.

| Lecture | What you build | What is still manual |
|---|---|---|
| **L1 — Docker** | Run the app in containers on your laptop | Build, run, stop — all manual |
| **L2 — Kubernetes** | Run the app in a local cluster with Kubernetes | `kubectl apply` every change, manual image import |
| **L3 — CI/CD** | Pipeline builds and pushes images automatically on every push | Update the manifest with the new image SHA, run `kubectl apply` manually |
| **L4 — Cloud** | EKS cluster in AWS, pipeline builds and deploys automatically | `git push` — nothing else |

The infrastructure itself — the cluster, the network, the nodes — is defined in Terraform files that live in the repository. The pipeline deploys to EKS automatically. The entire system, from code to running pod, is reproducible from scratch.

---

## Before You Start: 5 Questions

Make sure you can answer these before opening the Terraform files or the AWS console.

1. **What is the difference between a Region and an Availability Zone?**

2. **What does `terraform plan` do, and why run it before `terraform apply`?**

3. **Why does this lab use public subnets instead of private subnets?**

4. **What does the `LoadBalancer` service type give you that `NodePort` cannot?**

5. **What must you always run at the end of the lab, and why?**

If any of these are unclear, re-read the relevant section above before starting.
