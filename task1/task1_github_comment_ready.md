# Task 1 - Ianvs setup + PCB-AOI execution

## Goal

Validate that Ianvs can be installed and that the PCB-AOI single-task learning
fault-detection benchmark can run successfully.

## Environment

```text
Machine: Linux VM
OS: Ubuntu 24.04.4 LTS
User: root
Repository: https://github.com/kubeedge/ianvs.git
Repository path: /root/lfx-task1/ianvs
Ianvs commit: 95016dbf7699fac09a877c108133cb38f515119b
Python environment: /root/lfx-task1/ianvs-py37
Python version used for Ianvs: Python 3.7.12
```

Note: I initially checked Python on Windows, but Ianvs dependencies are old and
are not suitable for Python 3.14. I used a fresh Linux VM and a Python 3.7
virtual environment for the actual benchmark run.

## Setup summary

The repository was cloned and Ianvs was installed inside a dedicated virtual
environment:

```bash
git clone https://github.com/kubeedge/ianvs.git
cd ianvs

python3 --version

/root/lfx-task1/ianvs-py37/bin/python -m pip install -r requirements.txt
/root/lfx-task1/ianvs-py37/bin/python -m pip install -r examples/pcb-aoi/requirements.txt
/root/lfx-task1/ianvs-py37/bin/python -m pip install ./resources/third_party/sedna-0.6.0.1-py3-none-any.whl
/root/lfx-task1/ianvs-py37/bin/python -m pip install -e .

/root/lfx-task1/ianvs-py37/bin/ianvs --help
```

The `ianvs --help` command completed successfully, proving the Ianvs entry point
was available.

## PCB-AOI benchmark

Benchmark directory:

```bash
cd /root/lfx-task1/ianvs
cd examples/pcb-aoi/singletask_learning_bench/fault_detection
```

The benchmark was executed using the benchmark YAML from the PCB-AOI example:

```bash
cd /root/lfx-task1/ianvs
TMPDIR=/root/lfx-task1/tmp-run2 \
  /root/lfx-task1/ianvs-py37/bin/ianvs \
  -f ./examples/pcb-aoi/singletask_learning_bench/fault_detection/benchmarkingjob.yaml
```

## Issue encountered and fix

The first benchmark attempt failed because `/tmp` on the VM was a small tmpfs
mount and TensorFlow ran out of disk space while writing checkpoint files.

Error type:

```text
ResourceExhaustedError: No space left on device
```

Fix:

```bash
mkdir -p /root/lfx-task1/tmp-run2
TMPDIR=/root/lfx-task1/tmp-run2 ianvs -f ./examples/pcb-aoi/singletask_learning_bench/fault_detection/benchmarkingjob.yaml
```

This moved temporary TensorFlow/Ianvs files from `/tmp` to a filesystem with
enough free space.

## Successful result

The benchmark completed successfully and produced a leaderboard.

Final result:

```text
rank 1:
algorithm: fpn_singletask_learning
f1_score: 0.8697
paradigm: singletasklearning
basemodel: FPN
basemodel-momentum: 0.95
basemodel-learning_rate: 0.1

rank 2:
algorithm: fpn_singletask_learning
f1_score: 0.8604
paradigm: singletasklearning
basemodel: FPN
basemodel-momentum: 0.5
basemodel-learning_rate: 0.1
```

The terminal showed:

```text
Conversion is completed!
f1_score_avg: 0.8604
```

and then printed the final leaderboard table.

## Evidence attached

Please see the attached evidence files:

```text
task1-setup-transcript.txt
task1-benchmark-transcript.txt
task1.png
task1_compressed_2mb.mp4
```

The transcript files contain the full command history and terminal output. The
compressed video shows the benchmark run and successful result. The screenshot
captures the final leaderboard. The original uncompressed recording is also
available as `task1.mp4` if needed.
