# Task 2 - Simulation codebase bug identification

Repository: `kubeedge/ianvs`

Files studied:

- `core/testcasecontroller/simulation_system_admin/simulation_system_admin.py`
- `core/testcasecontroller/simulation/simulation.py`
- `core/cmd/obj/benchmarkingjob.py`
- `docs/proposals/simulation/simulation.md`
- `docs/proposals/simulation/sandbox-engine/sandbox-engine.md`

## Understanding of `simulation_system_admin.py`

The current file is a host-side helper for the old Ianvs simulation path. It is
supposed to check whether the local machine can build a kind/KubeEdge/Sedna
simulation environment, then call Sedna's `all-in-one.sh` script to create or
delete that environment.

Function roles:

1. `check_host_docker()`

   Intended role: check whether Docker is installed and usable. If Docker is not
   installed, it tries to install Docker through `get.docker.com`.

2. `check_host_kind()`

   Intended role: check whether `kind` is installed. If it is missing, it tries
   to download the `kind` binary and move it into `/usr/local/bin/kind`.

3. `get_host_free_memory_size()`

   Intended role: read `/proc/meminfo` and return host free memory in kB.

4. `check_host_memory()`

   Intended role: require at least 4 GB memory before simulation setup.

5. `get_host_number_of_cpus()`

   Intended role: read CPU count from `lscpu`.

6. `check_host_cpu()`

   Intended role: require at least 4 CPU cores before simulation setup.

7. `check_host_enviroment()`

   Intended role: run all host checks before building simulation. It calls
   Docker, kind, memory, and CPU checks.

8. `build_simulation_enviroment(simulation)`

   Intended role: validate the host environment, then call Sedna's
   `all-in-one.sh` script with simulation parameters:
   `NUM_CLOUD_WORKER_NODES`, `NUM_EDGE_NODES`, `KUBEEDGE_VERSION`,
   `SEDNA_VERSION`, and `CLUSTER_NAME`.

9. `destory_simulation_enviroment(simulation)`

   Intended role: call Sedna's `all-in-one.sh clean` path to delete the
   simulation environment.

## Difference between proposal and implementation

The simulation proposal says the Simulation System Administrator should:

- parse system config
- check Docker, kind, CPU, and memory
- build the simulation environment
- create and deploy modules needed in the simulation environment
- close and delete the simulation environment

The current implementation only partially does this. Config parsing is in
`simulation.py`, not in this file. Environment checks are present but fragile.
The build function only pipes a remote Sedna script into `bash`; it does not
deploy the Simulation Job Controller or validate that the cluster was actually
created. The destroy function exists, but the only caller path,
`BenchmarkingJob.run()`, never calls it after the benchmark.

The newer sandbox-engine proposal also expects:

- Docker daemon reachability, not just a `docker` command check
- kind availability
- at least 4 CPU cores
- at least 4 GB available memory
- `build_simulation_environment()` before sandbox execution
- `destroy_simulation_environment()` after all test cases

The bugs below are based on these gaps.

## BUG #1

Exact file/line:

`core/testcasecontroller/simulation_system_admin/simulation_system_admin.py:29-30`

Problem:

`check_host_docker()` can report Docker success even when Docker is not installed.

Why:

The function runs:

```python
shell_cmd = "docker version | head -n 2"
check_docker = subprocess.run(shell_cmd, shell=True, check=True)
```

This is a shell pipeline. Without `set -o pipefail`, the pipeline exit status is
the exit status of the last command, `head`, not `docker`. If `docker` is
missing, `head` can still return `0` after receiving empty input, so
`subprocess.run(..., check=True)` does not raise.

I reproduced this on a fresh Ubuntu VM where Docker was not installed:

```text
docker_on_path None
/bin/sh: 1: docker: not found
check_host_docker_returned
[INFO] - check docker successful
```

Impact:

The host environment check gives a false positive. Ianvs then continues toward
simulation setup on a machine that cannot run Docker, and the real failure is
delayed into the Sedna/kind setup.

Caller affected:

- `check_host_enviroment()` calls `check_host_docker()`
- `build_simulation_enviroment()` calls `check_host_enviroment()`
- `BenchmarkingJob.run()` calls `build_simulation_enviroment()` when simulation
  config is present

Deployment affected:

Fresh Linux VM, CI runner, or developer host where Docker is missing or where
the Docker daemon is not reachable.

Fix:

Check Docker directly and verify daemon reachability. Do not hide Docker's exit
code behind `head`.

```diff
+import shutil
+
 def check_host_docker():
-    shell_cmd = "docker version | head -n 2"
-    check_docker = subprocess.run(shell_cmd, shell=True, check=True)
-
-    if check_docker.returncode != 0:
-        # trying to install docker
-        LOGGER.info("trying to install docker")
-        try:
-            shell_install_docker = "curl -fsSL https://get.docker.com | \
-bash -s docker --mirror Aliyun"
-            install_docker = subprocess.run(
-                shell_install_docker, shell=True, check=True)
-
-            if install_docker.returncode == 0:
-                LOGGER.info("successfully installed docker")
-            else:
-                raise RuntimeError("install docker failed")
-        except Exception as err:
-            raise RuntimeError(f"install docker failed, error: {err}.") from err
+    if shutil.which("docker") is None:
+        LOGGER.info("trying to install docker")
+        try:
+            subprocess.run(
+                "set -o pipefail; curl -fsSL https://get.docker.com | "
+                "bash -s docker --mirror Aliyun",
+                shell=True,
+                executable="/bin/bash",
+                check=True,
+            )
+        except Exception as err:
+            raise RuntimeError(f"install docker failed, error: {err}.") from err
+
+    try:
+        subprocess.run(
+            ["docker", "info"],
+            stdout=subprocess.PIPE,
+            stderr=subprocess.PIPE,
+            text=True,
+            check=True,
+        )
+    except subprocess.CalledProcessError as err:
+        raise RuntimeError(f"docker daemon is not reachable: {err.stderr}") from err
 
     LOGGER.info("check docker successful")
```

## BUG #2

Exact file/line:

`core/testcasecontroller/simulation_system_admin/simulation_system_admin.py:113-118`

Problem:

`get_host_number_of_cpus()` crashes on modern Ubuntu instead of returning the CPU
count.

Why:

The function runs:

```python
shell_cmd = "lscpu | grep CPU:"
```

On Ubuntu 24.04, `lscpu` prints the CPU count as `CPU(s):`, not `CPU:`. The grep
therefore returns no line, and this parser fails:

```python
str(cpu_info).split(":")[1]
```

I reproduced this on the test VM:

```text
CPU(s):                                  4
Exact grep used by Ianvs returns:
<no output>
get_host_number_of_cpus
IndexError: list index out of range
```

Impact:

`check_host_cpu()` cannot validate a valid 4-core host. The simulation setup can
fail before cluster creation even though the machine satisfies the CPU
requirement.

Caller affected:

- `check_host_cpu()`
- `check_host_enviroment()`
- `build_simulation_enviroment()`
- `BenchmarkingJob.run()` when simulation config is enabled

Deployment affected:

Ubuntu 24.04 and other Linux distributions where `lscpu` uses `CPU(s):`.

Fix:

Use Python's OS APIs instead of parsing localized or version-dependent command
output.

```diff
+import os
+
 def get_host_number_of_cpus():
-    shell_cmd = "lscpu | grep CPU:"
-    with subprocess.Popen(shell_cmd, shell=True, stdout=subprocess.PIPE) as get_cpu_info:
-        cpu_info = get_cpu_info.stdout.read()
-        number_of_cpus = int(str(cpu_info).split(":")[
-                             1].strip().split("\\")[0])
-        return number_of_cpus
+    if hasattr(os, "sched_getaffinity"):
+        return len(os.sched_getaffinity(0))
+
+    number_of_cpus = os.cpu_count()
+    if number_of_cpus is None:
+        raise RuntimeError("unable to determine host CPU count")
+    return number_of_cpus
```

## BUG #3

Exact file/line:

`core/testcasecontroller/simulation_system_admin/simulation_system_admin.py:83-87`

Problem:

`get_host_free_memory_size()` uses `MemFree`, which is not the correct Linux
field for deciding whether a new workload has enough memory available.

Why:

Linux uses memory for buffers and filesystem cache. That memory is reclaimable
by applications, but it is not counted in `MemFree`. The kernel provides
`MemAvailable` for this exact question: how much memory is available for
starting a new workload without swapping.

On the test VM:

```text
MemFree:         5533400 kB
MemAvailable:  15159932 kB
```

The current Ianvs function returned only `5533400`, undercounting available
memory by almost 10 GB.

Impact:

`check_host_memory()` can falsely reject a healthy Linux host. This is likely on
long-running machines and CI runners where the page cache is large.

Caller affected:

- `check_host_memory()`
- `check_host_enviroment()`
- `build_simulation_enviroment()`
- `BenchmarkingJob.run()` when simulation config is enabled

Deployment affected:

Linux developer machines, CI runners, or long-running benchmark hosts with heavy
filesystem cache.

Fix:

Read `MemAvailable` from `/proc/meminfo`.

```diff
 def get_host_free_memory_size():
-    shell_cmd = "cat /proc/meminfo | grep MemFree"   # in kB
-    with subprocess.Popen(shell_cmd, shell=True, stdout=subprocess.PIPE) as get_memory_info:
-        memory_info = get_memory_info.stdout.read()
-        memory_free = int(str(memory_info).split(":")[1].strip().split(" ")[0])
-        return memory_free
+    with open("/proc/meminfo", "r", encoding="utf-8") as meminfo:
+        for line in meminfo:
+            key, value = line.split(":", 1)
+            if key == "MemAvailable":
+                return int(value.strip().split()[0])
+
+    raise RuntimeError("MemAvailable not found in /proc/meminfo")
```

## BUG #4

Exact file/line:

`core/testcasecontroller/simulation_system_admin/simulation_system_admin.py:157-166`

Problem:

`build_simulation_enviroment()` can report success even if the Sedna install
script is not downloaded.

Why:

The build command is a pipeline:

```python
shell_cmd = "curl https://raw.githubusercontent.com/kubeedge/sedna\
/master/scripts/installation/all-in-one.sh | " \
    f"NUM_CLOUD_WORKER_NODES={simulation.cloud_number} " \
    f"NUM_EDGE_NODES={simulation.edge_number} " \
    f"KUBEEDGE_VERSION={simulation.kubeedge_version} " \
    f"SEDNA_VERSION={simulation.sedna_version} " \
    f"CLUSTER_NAME={simulation.cluster_name} bash -"
```

There are two problems:

- `curl` is used without `-fS`.
- the pipeline is executed without `set -o pipefail`.

If `curl` fails because of a network issue, proxy block, TLS problem, or bad URL,
`bash -` may receive an empty script and exit successfully. Then
`subprocess.run(..., check=True)` can return success even though no cluster was
created.

Impact:

Ianvs can log:

```text
Congratulation! The simulation enviroment build successful!
```

even when the Sedna install script never ran. Later simulation job deployment
then fails because the expected kind/KubeEdge/Sedna environment does not exist.

Caller affected:

- `BenchmarkingJob.run()` calls `build_simulation_enviroment()`
- Any future Simulation Controller path that relies on this function before
  creating simulation jobs

Deployment affected:

Restricted corporate networks, CI without public internet, proxy environments,
or any host with transient GitHub/raw.githubusercontent.com connectivity issues.

Fix:

Fail fast on download errors, enable `pipefail`, and preferably use the same
branch as the destroy path.

```diff
-    shell_cmd = "curl https://raw.githubusercontent.com/kubeedge/sedna\
-/master/scripts/installation/all-in-one.sh | " \
+    shell_cmd = "set -o pipefail; curl -fsSL https://raw.githubusercontent.com/kubeedge/sedna\
+/main/scripts/installation/all-in-one.sh | " \
         f"NUM_CLOUD_WORKER_NODES={simulation.cloud_number} " \
         f"NUM_EDGE_NODES={simulation.edge_number} " \
         f"KUBEEDGE_VERSION={simulation.kubeedge_version} " \
         f"SEDNA_VERSION={simulation.sedna_version} " \
         f"CLUSTER_NAME={simulation.cluster_name} bash -"
 
     build_simulation_env_ret = subprocess.run(
-        shell_cmd, shell=True, check=True)
+        shell_cmd, shell=True, executable="/bin/bash", check=True)
```

Better replacement:

```python
import os

env = os.environ.copy()
env.update({
    "NUM_CLOUD_WORKER_NODES": str(simulation.cloud_number),
    "NUM_EDGE_NODES": str(simulation.edge_number),
    "KUBEEDGE_VERSION": simulation.kubeedge_version,
    "SEDNA_VERSION": simulation.sedna_version,
    "CLUSTER_NAME": simulation.cluster_name,
})

subprocess.run(
    "set -o pipefail; curl -fsSL "
    "https://raw.githubusercontent.com/kubeedge/sedna/main/scripts/installation/all-in-one.sh "
    "| bash -",
    shell=True,
    executable="/bin/bash",
    env=env,
    check=True,
)
```

## BUG #5

Exact file/line:

`core/cmd/obj/benchmarkingjob.py:86-94`

Related function:

`core/testcasecontroller/simulation_system_admin/simulation_system_admin.py:175-186`

Problem:

The simulation environment is built but never destroyed after the benchmark.

Why:

`BenchmarkingJob.run()` only calls the build function:

```python
if self.simulation is not None:
    build_simulation_enviroment(self.simulation)
```

There is no matching call to `destory_simulation_enviroment()` after the test
cases finish. There is also no `finally` block, so even if a test case fails, the
cluster cleanup path is skipped.

This contradicts the proposal flow, which says that after all test cases,
`destroy_simulation_environment()` should tear down the cluster.

Impact:

kind clusters, Sedna components, containers, networks, and temporary resources
can remain after Ianvs exits. Repeated runs can fail because the old cluster name
or ports are still in use. CI workers can also leak resources between jobs.

Caller affected:

`BenchmarkingJob.run()` is the only current integration point that calls the
simulation environment builder.

Deployment affected:

Developer VMs, repeated local experiments, and CI hosts where simulation jobs
are run more than once.

Fix:

Call the destroy function in a `finally` block after a successful build. This
uses the current misspelled function name to keep the fix small; a separate
cleanup can later add correctly spelled aliases.

```diff
-from core.testcasecontroller.simulation_system_admin import build_simulation_enviroment
+from core.testcasecontroller.simulation_system_admin import (
+    build_simulation_enviroment,
+    destory_simulation_enviroment,
+)
 
     def run(self):
         """
         run a end-to-end benchmarking job,
@@
         """
         self.workspace = os.path.join(self.workspace, self.name)
 
-        if self.simulation is not None:
-            build_simulation_enviroment(self.simulation)
-
-        self.test_env.prepare()
-
-        self.testcase_controller.build_testcases(test_env=self.test_env,
-                                                 test_object=self.test_object)
-
-        succeed_testcases, test_results = self.testcase_controller.run_testcases(self.workspace)
-
-        if test_results:
-            self.rank.save(succeed_testcases, test_results, output_dir=self.workspace)
-            self.rank.plot()
+        simulation_built = False
+        try:
+            if self.simulation is not None:
+                build_simulation_enviroment(self.simulation)
+                simulation_built = True
+
+            self.test_env.prepare()
+
+            self.testcase_controller.build_testcases(test_env=self.test_env,
+                                                     test_object=self.test_object)
+
+            succeed_testcases, test_results = self.testcase_controller.run_testcases(
+                self.workspace)
+
+            if test_results:
+                self.rank.save(succeed_testcases, test_results, output_dir=self.workspace)
+                self.rank.plot()
+        finally:
+            if simulation_built:
+                destory_simulation_enviroment(self.simulation)
```

