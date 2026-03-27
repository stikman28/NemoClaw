# Docker Resource Tuning for NemoClaw

## System Requirements

NemoClaw runs inside Docker via OpenShell. These guidelines help configure Docker
for stable operation across different hardware configurations.

### Minimum Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| **Docker Memory** | 2 GB | 4 GB | For NemoClaw sandbox + OpenShell gateway |
| **Docker CPUs** | 2 | 4 | Agent tool calls and inference are CPU-bound |
| **Free Disk** | 10 GB | 20 GB | Docker image (~3 GB) + build cache + volumes |
| **Host RAM** | 8 GB | 16 GB | Docker VM + host OS + IDE/browser |

### Component Memory Breakdown (Estimated)

| Component | Idle | Under Load | Notes |
|-----------|------|------------|-------|
| NemoClaw sandbox (Node.js + OpenClaw) | ~200 MB | ~500 MB | Agent processing + tool calls |
| OpenShell gateway | ~100 MB | ~200 MB | Request routing + policy enforcement |
| k3s (embedded in OpenShell) | ~300 MB | ~500 MB | Container orchestration |
| **NemoClaw total** | **~600 MB** | **~1.2 GB** | |

## Configuration by Host

### 8 GB Host (e.g., MacBook Air M1/M2 base)

This is a constrained environment. NemoClaw can run but requires careful management
of other Docker containers.

**Docker Desktop settings:**

- Memory: **4 GB** (Settings → Resources → Memory)
- CPUs: **4**
- Swap: **1 GB**

**Recommendations:**

- Stop non-essential containers before running NemoClaw
- Memory-heavy containers (e.g., database engines) can use 1-2 GB alone — stop them when not needed
- Run `docker system prune` regularly to reclaim disk
- Consider running NemoClaw OR other workloads, not all simultaneously

**Coexistence budget (4 GB Docker):**

| Scenario | Containers | Est. Memory | Fits? |
|----------|-----------|-------------|-------|
| NemoClaw only | sandbox + OpenShell | ~1.2 GB | Yes |
| NemoClaw + lightweight services | sandbox + OpenShell + API + DB + UI | ~1.5 GB | Yes |
| NemoClaw + heavy database | + SQL Server / Postgres with large datasets | ~3.3 GB | Tight |
| All workloads | everything | ~3.5 GB+ | Not recommended |

### 16 GB Host

Comfortable for all workloads simultaneously.

**Docker Desktop settings:**

- Memory: **8 GB**
- CPUs: **6**
- Swap: **2 GB**

### 32+ GB Host / DGX Spark

No constraints. Use defaults or allocate generously.

**Docker Desktop settings:**

- Memory: **12-16 GB**
- CPUs: **8+**

## Docker Cleanup

Reclaim disk space before installing NemoClaw:

```bash
# See what's using space
docker system df

# Remove unused images (keeps running containers' images)
docker image prune -a

# Remove build cache
docker builder prune

# Nuclear option — remove everything not currently running
docker system prune -a --volumes
```

**⚠ Warning:** `docker system prune -a --volumes` removes ALL stopped containers,
unused images, AND volumes. Only use this if you're sure no important data is in
Docker volumes. Application data (databases, vector stores) often lives in volumes.

**Safe cleanup (preserves volumes):**

```bash
docker system prune -a
```

This removes unused images and build cache but preserves data volumes.

## Blueprint Resource Limits

NemoClaw's blueprint can optionally set resource limits on the sandbox container.
Add to `blueprint.yaml` under `components.sandbox`:

```yaml
components:
  sandbox:
    image: "ghcr.io/nvidia/openshell-community/sandboxes/openclaw:latest"
    name: "openclaw"
    forward_ports:
      - 18789
    resources:
      memory: "1g"      # Hard limit — container killed if exceeded
      memory_swap: "2g"  # Memory + swap total
      cpus: "2.0"        # CPU cores allocated
```

These limits prevent the sandbox from consuming all available Docker memory,
which protects other containers running alongside it.

## Monitoring

Check container resource usage:

```bash
# Real-time stats
docker stats

# One-shot snapshot
docker stats --no-stream

# Check specific container
docker stats nemoclaw-sandbox --no-stream
```

## Troubleshooting

### "Killed" or OOMKilled

Container exceeded memory limit. Increase Docker VM memory or stop other containers.

### Slow agent responses

CPU contention. Check `docker stats` for CPU usage. Increase Docker CPU allocation
or stop CPU-intensive containers (database engines can use significant CPU).

### "No space left on device"

Docker disk full. Run `docker system prune -a` to reclaim space.
Check `docker system df` to see what's consuming disk.
