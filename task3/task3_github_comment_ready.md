# Task 3 - Container Isolation Capability Demonstration

## Goal

This bonus task demonstrates a small Docker-based sandbox runner. The runner
accepts:

- Docker image
- command
- CPU limit
- memory limit
- timeout

It runs the command inside a Docker container and returns structured execution
results containing:

- status
- exit code
- wall-clock time
- stdout
- stderr
- error message

It also detects Docker OOM termination through exit code `137`.

## Files created

```text
task3_sandbox/
├── sandbox_runner.py
├── README.md
├── evidence/
│   └── task3_execution_transcript.txt
└── task3_github_comment_ready.md
```

## Implementation summary

The program is implemented in `task3_sandbox/sandbox_runner.py`.

Main behavior:

1. Check whether Docker CLI exists and Docker daemon is reachable.
2. Create a unique container name:

   ```text
   ianvs-sandbox-<random-id>
   ```

3. Run Docker with isolation and resource limits:

   ```bash
   docker run \
     --name <container_name> \
     --network none \
     --cpus <cpu_limit> \
     --memory <memory_limit> \
     --memory-swap <memory_limit> \
     --pids-limit 256 \
     <image> \
     /bin/sh -lc "<command>"
   ```

4. Capture stdout, stderr, exit code, and wall-clock time.
5. If execution exceeds `--timeout`, remove the container with `docker rm -f`.
6. If exit code is `137`, return `status: "oom_killed"`.
7. Clean up the container after every run.

## Usage

```bash
python3 sandbox_runner.py \
  --image IMAGE \
  --command "COMMAND" \
  --cpu-limit CPU_LIMIT \
  --memory-limit MEMORY_LIMIT \
  --timeout TIMEOUT_SECONDS
```

## Example 1 - successful execution

Command:

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'print(\"hello from sandbox\")'" \
  --cpu-limit 1 \
  --memory-limit 256m \
  --timeout 10
```

Output:

```json
{
  "command": "python -c 'print(\"hello from sandbox\")'",
  "container_name": "ianvs-sandbox-88d7a7bbbbd4",
  "cpu_limit": "1",
  "error": "",
  "exit_code": 0,
  "image": "python:3.10-slim",
  "memory_limit": "256m",
  "status": "success",
  "stderr": "",
  "stdout": "hello from sandbox\n",
  "timeout_s": 10.0,
  "wall_time_s": 0.339
}
```

## Example 2 - OOM killed / exit code 137

Command:

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'a=[]; [a.append(bytearray(10*1024*1024)) for _ in range(1000)]'" \
  --cpu-limit 1 \
  --memory-limit 64m \
  --timeout 20
```

Output:

```json
{
  "command": "python -c 'a=[]; [a.append(bytearray(10*1024*1024)) for _ in range(1000)]'",
  "container_name": "ianvs-sandbox-7b8dab1d459d",
  "cpu_limit": "1",
  "error": "Container killed due to OOM (exit code 137). Consider increasing memory_limit.",
  "exit_code": 137,
  "image": "python:3.10-slim",
  "memory_limit": "64m",
  "status": "oom_killed",
  "stderr": "Killed\n",
  "stdout": "",
  "timeout_s": 20.0,
  "wall_time_s": 0.38
}
```

## Example 3 - timeout handling

Command:

```bash
python3 sandbox_runner.py \
  --image python:3.10-slim \
  --command "python -c 'import time; print(\"sleeping\"); time.sleep(20)'" \
  --cpu-limit 1 \
  --memory-limit 128m \
  --timeout 3
```

Output:

```json
{
  "command": "python -c 'import time; print(\"sleeping\"); time.sleep(20)'",
  "container_name": "ianvs-sandbox-1e6c0b769d53",
  "cpu_limit": "1",
  "error": "Container exceeded timeout of 3.0 seconds and was killed.",
  "exit_code": 137,
  "image": "python:3.10-slim",
  "memory_limit": "128m",
  "status": "timeout",
  "stderr": "",
  "stdout": "",
  "timeout_s": 3.0,
  "wall_time_s": 3.135
}
```

## Cleanup verification

Command:

```bash
docker ps -a --filter name=ianvs-sandbox --format "{{.Names}} {{.Status}}"
```

Output:

```text

```

No sandbox containers remained after the tests.

## Evidence files

```text
task3_execution_transcript.txt
task3.png
task3_2.png
task3_compressed_2mb.mp4
```

The compressed video is metadata-stripped and under 1 MB. The original
uncompressed recording is also available as `task3.mp4` if needed.

## Notes

- The sandbox disables container networking using `--network none`.
- The sandbox uses `--memory-swap` equal to `--memory-limit` so the memory limit
  is enforced clearly.
- The runner manually removes containers instead of relying only on `--rm`,
  because it needs to inspect whether Docker reported `.State.OOMKilled` before
  cleanup.
- Screenshots and video should be attached or referenced separately as visual
  evidence.
