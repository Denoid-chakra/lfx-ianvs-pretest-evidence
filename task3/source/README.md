# Task 3 - Mini Docker Sandbox

This is a small Python prototype for the Ianvs simulation sandbox bonus task.

It runs a command inside a Docker container with:

- Docker image selection
- command execution
- CPU limit
- memory limit
- timeout
- stdout capture
- stderr capture
- exit-code capture
- special handling for exit code `137` / OOM kill

The program prints one structured JSON result.

## Requirements

- Linux host
- Docker Engine installed and running
- Python 3

Check Docker:

```bash
docker --version
docker run --rm hello-world
```

## Usage

```bash
python3 sandbox_runner.py \
  --image IMAGE \
  --command "COMMAND" \
  --cpu-limit CPU_LIMIT \
  --memory-limit MEMORY_LIMIT \
  --timeout TIMEOUT_SECONDS
```

Arguments:

- `--image`: Docker image, for example `python:3.10-slim`
- `--command`: command executed inside the container using `/bin/sh -lc`
- `--cpu-limit`: CPU limit passed to Docker `--cpus`, for example `1` or `0.5`
- `--memory-limit`: memory limit passed to Docker `--memory`, for example `64m`
- `--timeout`: max wall-clock runtime in seconds

The runner also passes `--memory-swap` equal to `--memory-limit` so the memory
limit is enforced more clearly.

## Successful execution example

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'print(\"hello from sandbox\")'" \
  --cpu-limit 1 \
  --memory-limit 256m \
  --timeout 10
```

Expected status:

```json
{
  "status": "success",
  "exit_code": 0
}
```

## OOM execution example

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'a=[]; [a.append(bytearray(10*1024*1024)) for _ in range(1000)]'" \
  --cpu-limit 1 \
  --memory-limit 64m \
  --timeout 20
```

Expected status:

```json
{
  "status": "oom_killed",
  "exit_code": 137
}
```

## Timeout example

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'import time; time.sleep(20)'" \
  --cpu-limit 1 \
  --memory-limit 128m \
  --timeout 3
```

Expected status:

```json
{
  "status": "timeout"
}
```

## Design notes

The script creates a unique container name for every run:

```text
ianvs-sandbox-<random-id>
```

It removes the container after completion or timeout. On timeout, it forcibly
removes the container with `docker rm -f`.

The sandbox disables container networking with:

```bash
--network none
```

This keeps the prototype closer to an isolated execution environment.

