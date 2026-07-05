# Lecture 4: Cloud Deployment — AWS EKS + Terraform

## Overview

In Lecture 3 you built a GitLab CI pipeline that builds Docker images and pushes them to a registry. Every commit produces a tagged image. But deploying that image still requires someone to SSH into a server and run commands manually.

This lecture removes that last manual step. You will:

1. Write Terraform configuration that creates a real Kubernetes cluster on AWS (EKS)
2. Update your Kubernetes manifests to use dynamic image tags
3. Add a deploy stage to your pipeline so that `git push` goes all the way to production

By the end, your full delivery path is: code change → pipeline build → pipeline test → pipeline deploy → live on AWS.

---

## What Changes in This Lecture

The table below lists every file that changes or is created. Nothing else changes. There are no Helm charts, no multi-environment setup, no auto-scaling, and no HTTPS in this lecture — those come later.

| File | Change | Purpose |
|---|---|---|
| `terraform/versions.tf` | New | Terraform version and AWS provider pin |
| `terraform/variables.tf` | New | `aws_region` and `cluster_name` inputs |
| `terraform/main.tf` | New | VPC + EKS cluster (t3.micro, public subnets) |
| `terraform/outputs.tf` | New | `cluster_name`, `cluster_endpoint`, `configure_kubectl` |
| `kubernetes/backend-deployment.yml` | Modified | image uses `__IMAGE_TAG__` placeholder |
| `kubernetes/frontend-deployment.yml` | Modified | image uses `__IMAGE_TAG__` placeholder |
| `kubernetes/frontend-service.yml` | Modified | `type: LoadBalancer` (was NodePort) |
| `.gitlab-ci.yml` | Modified | Add `deploy` stage and `deploy` job |

---

## Prerequisites

Before starting this lecture you need:

- AWS account (free tier is sufficient)
- AWS CLI installed on your machine
- Terraform >= 1.6 installed on your machine
- `kubectl` installed (from Lecture 2)
- GitLab CI pipeline from Lecture 3 passing (build, test, push stages all green)

You also need an IAM user with the following AWS-managed policies attached:

- `AmazonEKSClusterPolicy`
- `AmazonEC2FullAccess`
- `AmazonVPCFullAccess`
- `IAMFullAccess`
- `AmazonEKSWorkerNodePolicy`

Step 2 below walks through creating this user.

---

## Core Concepts

### 1. Infrastructure as Code

**What it is:**
Infrastructure as Code (IaC) means describing your cloud infrastructure in text files instead of clicking through a web console. Your servers, networks, Kubernetes cluster, and load balancers are all defined in `.tf` files that live in your Git repository.

**Why it matters:**
- **Version control** — every infrastructure change is a commit with a message, author, and diff
- **Repeatability** — running `terraform apply` twice on the same files produces the same infrastructure
- **Code review** — your team reviews infrastructure changes the same way they review application code
- **Disaster recovery** — if your AWS account is accidentally deleted, you can recreate everything from the files in your repository

Without IaC, you are one person away from losing all knowledge of how your infrastructure is built. With IaC, the files are the documentation.

**How it works:**
You write `.tf` files describing the desired state. Then:
- `terraform plan` compares your files against what currently exists in AWS and shows you what will change
- `terraform apply` makes the changes
- `terraform destroy` removes everything

**Common mistake:**
Editing the `.tfstate` file manually. The state file is Terraform's internal record of what it created. If you edit it, Terraform loses track of what exists and may try to create duplicates or fail to destroy resources. Never touch `.tfstate` by hand.

---

### 2. Terraform Modules

**What they are:**
Terraform modules are reusable packages of Terraform configuration, similar to functions in programming. Instead of writing every AWS resource yourself, you call a module that someone else wrote and tested.

**Why they matter:**
Creating an EKS cluster from scratch requires 20+ separate AWS resources: IAM roles for the control plane, IAM roles for worker nodes, security groups, node groups, add-ons, OIDC providers, and more. The `terraform-aws-modules/eks/aws` module packages all of this into a single block with sensible defaults.

**How they work:**
```hcl
module "eks" {
  source  = "registry.terraform.io/terraform-aws-modules/eks/aws"
  version = "20.8.5"

  cluster_name = var.cluster_name
  # ... other inputs
}
```

The `source` is the module location (Terraform registry). The `version` pins the exact module version you want.

**Common mistake:**
Omitting `version`. Without a version pin, Terraform fetches the latest module version when you run `terraform init`. This can silently break your configuration when the module authors release a new version with different behavior. Always pin versions — the same principle as pinning Docker image tags.

---

### 3. Amazon EKS

**What it is:**
Amazon Elastic Kubernetes Service (EKS) is a managed Kubernetes control plane. You supply the worker nodes (EC2 instances). AWS runs the API server, etcd, scheduler, and controller manager on your behalf.

**Why it matters:**
Running your own Kubernetes control plane requires at minimum three virtual machines for high availability, plus ongoing patching, certificate rotation, and etcd backup management. AWS does all of this for $0.10 per hour per cluster. For a lab environment the cost is negligible.

Your worker nodes — the EC2 instances that actually run your pods — are still billed normally. This is why choosing the right instance type matters.

**How it works:**
The `module "eks"` block in `main.tf` defines:
- The cluster name and Kubernetes version
- Which subnets the worker nodes live in
- The EC2 instance type for worker nodes
- How many worker nodes to create

After `terraform apply`, you run `aws eks update-kubeconfig` to add the cluster credentials to your local `~/.kube/config`, and then `kubectl` works normally.

**Common mistake:**
Using large instance types unnecessarily. A `t3.large` costs roughly 10x more than a `t3.micro`. For this lab, `t3.micro` is sufficient. One node with one CPU and 1GB of RAM is enough to run the frontend and backend deployments.

---

### 4. LoadBalancer Service

**What it is:**
A Kubernetes Service of type `LoadBalancer` asks your cloud provider to provision a load balancer and assign it a public DNS name. Traffic to that DNS name is forwarded to your pods.

**Why it matters:**
In Lecture 2 you used `NodePort`, which exposes a port on each worker node. To access your application, you need to know the IP address of a worker node and the port number. This is fragile: node IPs change when nodes are replaced, and port numbers are hard to remember.

`LoadBalancer` gives you a stable public DNS name. AWS provisions an Elastic Load Balancer automatically. The DNS name stays the same even if all your worker nodes are replaced.

**How it works:**
Change `type: NodePort` to `type: LoadBalancer` in your service manifest. Remove the `nodePort` field. Apply the manifest. EKS detects the service type and calls the AWS API to create an ELB. After 2-3 minutes, `kubectl get svc` shows an EXTERNAL-IP (which is actually a DNS name, not an IP).

**Common mistake:**
Running `kubectl get svc` immediately after `kubectl apply` and panicking when EXTERNAL-IP shows `<pending>`. The ELB provisioning takes 2-3 minutes. Wait, then check again.

---

### 5. Automated Deploy in Pipeline

**What it is:**
A deploy stage in your CI/CD pipeline that runs `kubectl apply` against your EKS cluster automatically when code merges to main.

**Why it matters:**
Before this stage, your pipeline builds and tests code, but a human still has to run `kubectl apply` to deploy. The deploy stage removes this manual step. After this lecture, a merged pull request automatically deploys to AWS within minutes.

**How it works:**
The pipeline job uses the `alpine/k8s:1.29.2` Docker image, which contains both the AWS CLI and `kubectl`. The job:
1. Runs `aws eks update-kubeconfig` to configure kubectl credentials using environment variables
2. Uses `sed` to replace `__IMAGE_TAG__` in the manifest files with the actual commit SHA
3. Runs `kubectl apply` on all manifests
4. Runs `kubectl rollout status` to wait for the deployment to complete

The AWS credentials come from GitLab CI/CD variables (masked), not from hardcoded values in the pipeline file.

**Common mistake:**
Forgetting to add the `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `CLUSTER_NAME` variables to GitLab CI/CD settings. The pipeline will fail with authentication errors. Step 7 covers exactly how to add these.

---

## Step-by-Step Instructions

### Step 1: Install and Verify Tools

Before writing any code, verify that all required tools are installed.

**Check existing installations:**
```bash
aws --version
terraform --version
kubectl version --client
```

Expected output (versions may differ slightly):
```
aws-cli/2.15.0 Python/3.11.6 Darwin/23.0.0 ...
Terraform v1.7.0
Client Version: v1.29.2
```

**Install on macOS (if not installed):**
```bash
brew install awscli
brew tap hashicorp/tap && brew install hashicorp/tap/terraform
```

**Install on Windows (if not installed):**
```powershell
winget install Amazon.AWSCLI
winget install Hashicorp.Terraform
```

After installing, open a new terminal window and run the version checks again to confirm.

---

### Step 2: Create IAM User and Configure AWS Credentials

You need an AWS IAM user with programmatic access. Do not use your AWS root account.

**In the AWS Console:**

1. Go to **IAM > Users > Create user**
2. Enter username: `shoplist-devops`
3. Select **Programmatic access only** (no console access needed)
4. Click **Next: Permissions**
5. Choose **Attach policies directly**
6. Search for and attach each of these policies:
   - `AmazonEKSClusterPolicy`
   - `AmazonEC2FullAccess`
   - `AmazonVPCFullAccess`
   - `IAMFullAccess`
   - `AmazonEKSWorkerNodePolicy`
7. Click through to **Create user**
8. On the final screen, go to the user's **Security credentials** tab
9. Click **Create access key**
10. Select **Command Line Interface (CLI)**
11. Click through and **Download .csv file** — save this file securely. You cannot retrieve the secret key again.

**Configure the AWS CLI:**
```bash
aws configure
```

You will be prompted for four values:
```
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: eu-west-1
Default output format [None]: json
```

**Verify the configuration:**
```bash
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDIODR4TAW7CSEXAMPLE",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/shoplist-devops"
}
```

If you see your account ID and username, your credentials are working correctly.

---

### Step 3: Write the Terraform Files

Create the `terraform/` directory in your project root:
```bash
mkdir terraform
```

Create each of the following four files exactly as shown.

**`terraform/versions.tf`**
```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

This file declares the minimum Terraform version and pins the AWS provider to the 5.x family. The `~>` operator means "5.anything but not 6.0".

---

**`terraform/variables.tf`**
```hcl
variable "aws_region" {
  description = "AWS region where the EKS cluster will be created"
  type        = string
  default     = "eu-west-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "shoplist"
}
```

These two variables are all you need. Everything else in `main.tf` uses these two values or hardcoded constants. You can override them at apply time with `-var` flags if needed.

---

**`terraform/main.tf`**
```hcl
provider "aws" {
  region = var.aws_region
}

data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

module "vpc" {
  source  = "registry.terraform.io/terraform-aws-modules/vpc/aws"
  version = "5.5.1"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnets = []

  enable_nat_gateway = false
  enable_vpn_gateway = false

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  tags = {
    Project = var.cluster_name
  }
}

module "eks" {
  source  = "registry.terraform.io/terraform-aws-modules/eks/aws"
  version = "20.8.5"

  cluster_name    = var.cluster_name
  cluster_version = "1.29"

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.public_subnets
  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    default = {
      min_size       = 1
      max_size       = 1
      desired_size   = 1
      instance_types = ["t3.micro"]
    }
  }

  tags = {
    Project = var.cluster_name
  }
}
```

A few things to notice:

- `enable_nat_gateway = false` — NAT gateways cost money. Worker nodes are in public subnets so they can pull images directly. This is fine for a lab; production clusters put nodes in private subnets.
- `public_subnet_tags` with `kubernetes.io/role/elb = 1` — EKS requires this tag to know which subnets to use when creating load balancers for `LoadBalancer` services.
- `cluster_endpoint_public_access = true` — your laptop needs to reach the API server to run `kubectl`. In production you would restrict this.
- `desired_size = 1`, `instance_types = ["t3.micro"]` — one tiny node is enough for the lab.

---

**`terraform/outputs.tf`**
```hcl
output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Endpoint of the EKS cluster API server"
  value       = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Command to configure kubectl to use this cluster"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}
```

The `configure_kubectl` output is a convenience — after `terraform apply` finishes, you can copy and paste the exact command to configure kubectl.

---

### Step 4: Create the Cluster

Navigate into the terraform directory and initialize:
```bash
cd terraform
terraform init
```

`terraform init` downloads the module source code and provider plugins. You will see output like:
```
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/eks/aws 20.8.5...
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 5.5.1...
...
Terraform has been successfully initialized!
```

Preview what will be created:
```bash
terraform plan
```

The plan output will show roughly 50 resources that will be created (IAM roles, VPC, subnets, security groups, EKS cluster, node group). Review it and confirm there are no unexpected changes.

Apply the configuration:
```bash
terraform apply
```

Terraform will show the plan again and ask for confirmation:
```
Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only 'yes' will be accepted to approve.

  Enter a value: yes
```

Type `yes` and press Enter.

**This takes 12-15 minutes.** The EKS control plane takes approximately 10 minutes to provision, and the node group takes another 2-3 minutes. This is normal. Do not interrupt the process.

When complete, you will see output similar to:
```
Apply complete! Resources: 52 added, 0 changed, 0 destroyed.

Outputs:

cluster_endpoint = "https://ABCDEF1234567890.gr7.eu-west-1.eks.amazonaws.com"
cluster_name = "shoplist"
configure_kubectl = "aws eks update-kubeconfig --name shoplist --region eu-west-1"
```

---

### Step 5: Connect kubectl to the Cluster

Copy the `configure_kubectl` output from the previous step and run it:
```bash
aws eks update-kubeconfig --name shoplist --region eu-west-1
```

Expected output:
```
Added new context arn:aws:eks:eu-west-1:123456789012:cluster/shoplist to /Users/yourname/.kube/config
```

Verify the cluster is reachable:
```bash
kubectl get nodes
```

Expected output (wait up to 2 minutes if the node is still initializing):
```
NAME                                        STATUS   ROLES    AGE   VERSION
ip-10-0-1-45.eu-west-1.compute.internal    Ready    <none>   2m    v1.29.0-eks-5e0fdde
```

You should see exactly one node with STATUS `Ready`. If it shows `NotReady`, wait 30 seconds and try again.

---

### Step 6: Update the Kubernetes Manifests

Three files need to change.

**`kubernetes/frontend-service.yml` — change NodePort to LoadBalancer**

Find the `spec` section and change the `type` field. Also remove the `nodePort` line under `ports` if it exists:
```yaml
spec:
  selector:
    app: frontend
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 3000
      protocol: TCP
```

The `nodePort` field is only valid for `NodePort` services. Remove it entirely.

**`kubernetes/backend-deployment.yml` — add image tag placeholder**

Find the `image` field in the container spec. Change it to use `__IMAGE_TAG__` as the tag:
```yaml
containers:
  - name: backend
    image: registry.gitlab.com/your-group/shoplist/backend:__IMAGE_TAG__
```

Replace `registry.gitlab.com/your-group/shoplist/backend` with your actual registry path. Keep `:__IMAGE_TAG__` exactly as written — the pipeline will replace this string at deploy time.

**`kubernetes/frontend-deployment.yml` — add image tag placeholder**

Same change:
```yaml
containers:
  - name: frontend
    image: registry.gitlab.com/your-group/shoplist/frontend:__IMAGE_TAG__
```

The `__IMAGE_TAG__` placeholder is a pattern (double underscores, uppercase) chosen to be unlikely to appear naturally in a YAML file. The deploy job uses `sed` to replace it.

---

### Step 7: Add CI/CD Variables in GitLab

The deploy job needs AWS credentials to authenticate with EKS. These must be stored as GitLab CI/CD variables, not in any file in your repository.

In your GitLab project:
1. Go to **Settings > CI/CD**
2. Expand the **Variables** section
3. Click **Add variable** for each of the following:

| Key | Value | Masked | Protected |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | Your access key ID | Yes | Yes |
| `AWS_SECRET_ACCESS_KEY` | Your secret access key | Yes | Yes |
| `AWS_REGION` | `eu-west-1` | No | Yes |
| `CLUSTER_NAME` | `shoplist` | No | Yes |

**Important:** Set `AWS_SECRET_ACCESS_KEY` as **Masked**. This prevents the secret from appearing in pipeline logs even if a job accidentally prints all environment variables.

Setting variables as **Protected** means they are only available to protected branches (like `main`). This ensures the deploy job can only run on main, not on feature branches.

---

### Step 8: Add the Deploy Stage to .gitlab-ci.yml

Open `.gitlab-ci.yml`. Add `deploy` to the `stages` list:
```yaml
stages:
  - build
  - test
  - push
  - deploy
```

Then add the deploy job at the end of the file:
```yaml
deploy:
  stage: deploy
  image: alpine/k8s:1.29.2
  script:
    - aws eks update-kubeconfig --name $CLUSTER_NAME --region $AWS_REGION
    - |
      for file in kubernetes/*.yml; do
        sed "s|__IMAGE_TAG__|$CI_COMMIT_SHORT_SHA|g" "$file" | kubectl apply -f -
      done
    - kubectl rollout status deployment/backend -n shoplist --timeout=120s
    - kubectl rollout status deployment/frontend -n shoplist --timeout=120s
  needs:
    - verify-registry
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
```

A few things to note:

- `image: alpine/k8s:1.29.2` — this image contains both the AWS CLI and kubectl. You do not need to install them in the script.
- `aws eks update-kubeconfig` — this uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from the CI/CD variables automatically. The AWS CLI picks them up from environment variables.
- `sed "s|__IMAGE_TAG__|$CI_COMMIT_SHORT_SHA|g"` — GitLab provides `$CI_COMMIT_SHORT_SHA` automatically. It is the first 8 characters of the commit hash. This becomes the image tag for this deployment.
- `kubectl rollout status --timeout=120s` — this waits up to 2 minutes for the deployment to finish. If pods fail to start, the pipeline fails here, giving you a clear signal before the job completes.
- `needs: [verify-registry]` — the deploy job waits for the image push to complete before running.
- `rules: if: $CI_COMMIT_BRANCH == "main"` — the deploy job only runs on the main branch. Feature branch pushes skip this job.

If your previous stages use a different job name than `verify-registry` for the push/verify step, update `needs` accordingly.

---

### Step 9: Push and Verify the Deployment

Stage all the changed files:
```bash
git add terraform/ kubernetes/ .gitlab-ci.yml
git commit -m "feat: cloud deployment with EKS and Terraform"
git push origin main
```

**Watch the pipeline in GitLab:**

Go to your project in GitLab > **CI/CD > Pipelines**. You should see a new pipeline running with four stages: build, test, push, deploy.

The first three stages complete in about 2-3 minutes. The deploy stage takes approximately 5 minutes (image pull + pod startup).

All four stages should show green checkmarks.

**Get the application URL:**

After the pipeline completes, run:
```bash
kubectl get svc frontend -n shoplist
```

Expected output:
```
NAME       TYPE           CLUSTER-IP      EXTERNAL-IP                                              PORT(S)        AGE
frontend   LoadBalancer   172.20.45.123   a1b2c3d4e5f6.eu-west-1.elb.amazonaws.com   80:31234/TCP   3m
```

Copy the value in the `EXTERNAL-IP` column. If it shows `<pending>`, wait 2-3 minutes for AWS to provision the load balancer and run the command again.

Open `http://a1b2c3d4e5f6.eu-west-1.elb.amazonaws.com` in your browser. You should see the ShopList application running on AWS.

---

## Destroying Resources

> **This section is mandatory. Read it before starting the lab.**

EKS costs approximately $0.10 per hour for the control plane. One `t3.micro` node costs approximately $0.01 per hour. Left running for a full day, this costs around $3. Left running for a month, around $85.

**At the end of every lab session, destroy all resources:**

Delete the Kubernetes namespace (this removes all pods, services, and deployments):
```bash
kubectl delete namespace shoplist
```

Destroy all Terraform-managed resources:
```bash
cd /path/to/your/project/terraform
terraform destroy
```

Terraform will show you everything it plans to delete and ask for confirmation. Type `yes`.

This takes approximately 10-15 minutes. Wait for it to complete fully.

**Verify destruction in the AWS Console:**

- Go to **EKS > Clusters** — the list should be empty
- Go to **EC2 > Instances** — there should be no running instances related to your cluster
- Go to **EC2 > Load Balancers** — the ELB created by your LoadBalancer service should be gone

If `terraform destroy` fails with an error about load balancers, the ELB created by Kubernetes may still exist. In that case:
1. Delete the load balancer manually in the AWS Console under **EC2 > Load Balancers**
2. Run `terraform destroy` again

The ELB is created by Kubernetes (not Terraform), so Terraform does not always know to delete it first.

---

## Appendix: GitHub Users

If your project is on GitHub rather than GitLab, the pipeline steps are equivalent but use GitHub Actions syntax.

**Add repository secrets** (Settings > Secrets and variables > Actions > New repository secret):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

**Add a deploy job to `.github/workflows/ci.yml`:**
```yaml
deploy:
  name: Deploy to EKS
  runs-on: ubuntu-latest
  needs: verify-registry
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: actions/checkout@v4

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: eu-west-1

    - name: Configure kubectl
      run: aws eks update-kubeconfig --name shoplist --region eu-west-1

    - name: Deploy manifests
      run: |
        for file in kubernetes/*.yml; do
          sed "s|__IMAGE_TAG__|${GITHUB_SHA::8}|g" "$file" | kubectl apply -f -
        done

    - name: Wait for rollout
      run: |
        kubectl rollout status deployment/backend -n shoplist --timeout=120s
        kubectl rollout status deployment/frontend -n shoplist --timeout=120s
```

The `aws-actions/configure-aws-credentials@v4` action handles authentication. The rest of the deploy logic is identical to the GitLab version.

---

## Interview Questions

These are common DevOps interview questions that this lecture prepares you to answer confidently.

**1. What is Infrastructure as Code, and why is it better than clicking in the console?**

Infrastructure as Code means defining cloud resources in text files that are version-controlled alongside application code. It is better than clicking in the console because: changes are tracked in Git with author, timestamp, and commit message; the same configuration can be applied to create identical environments (dev, staging, production); infrastructure changes go through code review like any other change; if an environment is lost, it can be recreated from the files. Clicking in the console produces undocumented, unrepeatable, unreviewable changes.

**2. What does `terraform plan` do and why run it before `apply`?**

`terraform plan` compares the desired state described in your `.tf` files against the current state stored in the `.tfstate` file and queries AWS to find the actual current state. It then shows you exactly what will be created, changed, or destroyed — without making any changes. You run `plan` before `apply` to catch mistakes before they affect real infrastructure. A `plan` might reveal that a change you thought was safe will destroy and recreate a database, which is a very different outcome than a rolling update.

**3. What is the difference between a LoadBalancer service and a NodePort service?**

A `NodePort` service opens a port on every worker node. To reach your application, you need to know a worker node's IP address and the assigned port number. If the node is replaced, the IP changes. A `LoadBalancer` service asks the cloud provider to create a load balancer with a stable public DNS name. Traffic to that DNS name is forwarded to healthy pods automatically. The DNS name stays the same regardless of what happens to individual nodes. `LoadBalancer` is the correct choice for production workloads exposed to the internet.

**4. How does the deploy stage get AWS credentials securely without hardcoding them?**

AWS credentials are stored as masked CI/CD variables in GitLab (or repository secrets in GitHub). They are injected into the pipeline job as environment variables at runtime. The AWS CLI automatically reads `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from environment variables — no configuration file is needed. The credentials never appear in any file in the repository, never appear in pipeline logs (because they are masked), and are only available to protected branches.

**5. What does `__IMAGE_TAG__` mean and how does it get replaced in the pipeline?**

`__IMAGE_TAG__` is a placeholder string in the Kubernetes manifest files. The double underscores and uppercase letters are a convention that makes it visually obvious and unlikely to appear naturally in a YAML file. In the deploy job, `sed` replaces every occurrence of `__IMAGE_TAG__` with the actual commit SHA (`$CI_COMMIT_SHORT_SHA` in GitLab, `${GITHUB_SHA::8}` in GitHub Actions). This means each deployment uses the exact image that was built from that specific commit, providing a clear link between what is running in production and which commit produced it. The manifests committed to Git always contain the placeholder, never a real tag — the substitution happens only in the pipeline's memory during the deploy job.
