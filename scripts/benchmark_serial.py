#!/usr/bin/env python3
"""Compare two StringTie binaries under a verified, sampled one-thread constraint.

Build BOTH binaries with NOTHREADS and disable any HTSlib worker setup first.
The -p 1 argument alone does not enforce one operating-system thread.
Only measured runs contribute to statistics; warmups and thread probes do not.
"""

import argparse
import collections
import ctypes
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time


class BenchmarkError(RuntimeError):
    pass


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gtf_fingerprint(path):
    """Discard only whole #comment lines; retain order, whitespace and newlines."""
    if not path.is_file():
        raise BenchmarkError(f"Missing output GTF: {path}")
    digest = hashlib.sha256()
    data_rows = 0
    normalized_bytes = 0
    with path.open("rb") as stream:
        for line in stream:
            if line.startswith(b"#"):
                continue
            digest.update(line)
            normalized_bytes += len(line)
            if line.strip():
                data_rows += 1
    if not data_rows:
        raise BenchmarkError(f"Empty or comment-only output GTF: {path}")
    return {
        "sha256": digest.hexdigest(),
        "data_rows": data_rows,
        "normalized_bytes": normalized_bytes,
    }


class ProcTaskInfo(ctypes.Structure):
    # Darwin SDK sys/proc_info.h, struct proc_taskinfo; PROC_PIDTASKINFO == 4.
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in ("virtual_size", "resident_size", "total_user", "total_system",
                     "threads_user", "threads_system")
    ] + [
        (name, ctypes.c_int32)
        for name in ("policy", "faults", "pageins", "cow_faults", "messages_sent",
                     "messages_received", "syscalls_mach", "syscalls_unix", "csw",
                     "threadnum", "numrunning", "priority")
    ]


def make_thread_counter():
    if sys.platform == "darwin":
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        get_info = libproc.proc_pidinfo
        get_info.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                             ctypes.c_void_p, ctypes.c_int]
        get_info.restype = ctypes.c_int

        def count(pid):
            info = ProcTaskInfo()
            ctypes.set_errno(0)
            size = get_info(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
            if size != ctypes.sizeof(info):
                error = ctypes.get_errno()
                if error == errno.ESRCH:
                    return None  # exited between wait4 and proc_pidinfo
                raise BenchmarkError(
                    f"proc_pidinfo({pid}) returned {size} bytes; errno={error}")
            return info.threadnum if info.threadnum > 0 else None

        return count, "Darwin proc_pidinfo(PROC_PIDTASKINFO).pti_threadnum"
    if sys.platform.startswith("linux"):
        def count(pid):
            try:
                return len(list(Path(f"/proc/{pid}/task").iterdir())) or None
            except FileNotFoundError:
                return None
        return count, "Linux /proc/PID/task"
    raise BenchmarkError("Thread verification supports macOS and Linux only")


def host_metadata():
    info = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version,
        "logical_cpu_count": os.cpu_count(),
        "processor": platform.processor(),
    }
    if sys.platform == "darwin":
        for field in ("machdep.cpu.brand_string", "hw.model", "hw.memsize",
                      "hw.physicalcpu", "hw.logicalcpu"):
            value = subprocess.run(["sysctl", "-n", field], text=True,
                                   capture_output=True, check=False)
            if value.returncode == 0:
                info[field] = value.stdout.strip()
    elif sys.platform.startswith("linux"):
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text().splitlines():
                if line.startswith(("model name", "Hardware")):
                    info["cpu_model"] = line.partition(":")[2].strip()
                    break
        if hasattr(os, "sched_getaffinity"):
            info["cpu_affinity"] = sorted(os.sched_getaffinity(0))
    info["environment"] = {
        key: os.environ[key] for key in
        ("LANG", "LC_ALL", "LC_NUMERIC", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
         "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "DYLD_INSERT_LIBRARIES",
         "LD_PRELOAD") if key in os.environ
    }
    return info


def save_report(output_dir, report):
    temporary = output_dir / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(output_dir / "report.json")


def run_once(label, binary, input_path, output_dir, run_id, extra_args,
             thread_counter=None, probe_interval=0.002):
    """Use wait4 for this child, avoiding cumulative RUSAGE_CHILDREN subtraction."""
    output = output_dir / f"{run_id}-{label}.gtf"
    stdout_path = output_dir / f"{run_id}-{label}.stdout.log"
    stderr_path = output_dir / f"{run_id}-{label}.stderr.log"
    if output.exists():
        raise BenchmarkError(f"Refusing to reuse an existing GTF: {output}")
    command = [str(binary), "-p", "1", *extra_args, str(input_path), "-o", str(output)]
    record = {"label": label, "run_id": run_id, "command": command,
              "output": str(output), "stdout": str(stdout_path),
              "stderr": str(stderr_path)}
    samples = collections.Counter()
    first_sample_s = None
    last_sample_s = None
    child = None
    reaped = False
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        start = time.perf_counter()
        try:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr)
            if thread_counter is None:
                _, status, usage = os.wait4(child.pid, 0)
            else:
                while True:
                    pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                    if pid:
                        break
                    count = thread_counter(child.pid)
                    if count is not None:
                        samples[count] += 1
                        elapsed = time.perf_counter() - start
                        if first_sample_s is None:
                            first_sample_s = elapsed
                        last_sample_s = elapsed
                    time.sleep(probe_interval)
            elapsed = time.perf_counter() - start
            reaped = True
            child.returncode = os.waitstatus_to_exitcode(status)
            record.update({
                "exit_code": child.returncode,
                "wall_seconds": elapsed,
                "user_seconds": usage.ru_utime,
                "system_seconds": usage.ru_stime,
                "cpu_seconds": usage.ru_utime + usage.ru_stime,
                "peak_rss_bytes": int(usage.ru_maxrss if sys.platform == "darwin"
                                      else usage.ru_maxrss * 1024),
                "voluntary_context_switches": usage.ru_nvcsw,
                "involuntary_context_switches": usage.ru_nivcsw,
            })
        finally:
            if child is not None and not reaped:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
                try:
                    _, status, _ = os.wait4(child.pid, 0)
                    child.returncode = os.waitstatus_to_exitcode(status)
                except ChildProcessError:
                    pass
    if thread_counter is not None:
        record["thread_probe"] = {
            "sample_interval_seconds": probe_interval,
            "observations_by_thread_count": dict(sorted(samples.items())),
            "samples": sum(samples.values()),
            "minimum_observed": min(samples) if samples else None,
            "maximum_observed": max(samples) if samples else None,
            "first_sample_seconds": first_sample_s,
            "last_sample_seconds": last_sample_s,
        }
    # Return even a failed process's measurements so the caller can persist them.
    return record


def validate_run(record, expected_hash):
    if record["exit_code"] != 0:
        raise BenchmarkError(
            f"{record['run_id']} {record['label']} exited {record['exit_code']}; "
            f"see {record['stderr']}")
    fingerprint = gtf_fingerprint(Path(record["output"]))
    record["gtf"] = fingerprint
    if expected_hash is not None and fingerprint["sha256"] != expected_hash:
        raise BenchmarkError(
            f"GTF mismatch: {record['run_id']} {record['label']}: "
            f"{fingerprint['sha256']} != {expected_hash}")
    probe = record.get("thread_probe")
    if probe is not None and (probe["samples"] == 0 or
                              probe["minimum_observed"] != 1 or
                              probe["maximum_observed"] != 1):
        raise BenchmarkError(
            f"{record['label']} did not pass one-thread verification: "
            f"{probe['observations_by_thread_count']}")
    record["correctness"] = "pass"
    return fingerprint["sha256"]


def summarize(runs):
    measurements = [run for run in runs if run["phase"] == "measurement"]
    result = {}
    for label in ("baseline", "candidate"):
        group = [run for run in measurements if run["label"] == label]
        result[label] = {}
        for metric in ("wall_seconds", "user_seconds", "system_seconds",
                       "cpu_seconds", "peak_rss_bytes"):
            values = [run[metric] for run in group]
            result[label][metric] = {"median": statistics.median(values),
                                     "min": min(values), "max": max(values),
                                     "values_in_run_order": values}
    baseline_wall = result["baseline"]["wall_seconds"]["median"]
    candidate_wall = result["candidate"]["wall_seconds"]["median"]
    result["wall_speedup_ratio_of_medians"] = baseline_wall / candidate_wall
    result["wall_time_reduction_percent"] = 100 * (1 - candidate_wall / baseline_wall)
    candidate_cpu = result["candidate"]["cpu_seconds"]["median"]
    result["cpu_speedup_ratio_of_medians"] = (
        result["baseline"]["cpu_seconds"]["median"] / candidate_cpu
        if candidate_cpu else None)
    pairs = collections.defaultdict(dict)
    for run in measurements:
        pairs[run["repetition"]][run["label"]] = run["wall_seconds"]
    ratios = [pair["baseline"] / pair["candidate"] for pair in pairs.values()]
    result["per_pair_wall_speedups"] = ratios
    result["median_of_per_pair_wall_speedups"] = statistics.median(ratios)
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Must not already exist")
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--extra-arg", action="append", default=[],
                        help="Shared argument, e.g. --extra-arg=-L; never overrides -p/-o")
    args = parser.parse_args(argv)
    if args.repetitions < 1 or args.warmups < 0:
        parser.error("repetitions must be positive and warmups nonnegative")
    for arg in args.extra_arg:
        if arg == "--" or arg.startswith(("-p", "-o", "--threads", "--output")):
            parser.error("extra arguments must not override thread or output options")
    for field in ("baseline", "candidate", "input"):
        path = getattr(args, field).resolve(strict=True)
        if not path.is_file():
            parser.error(f"{field} must be a regular file")
        if field != "input" and not os.access(path, os.X_OK):
            parser.error(f"{field} is not executable: {path}")
        setattr(args, field, path)
    args.output_dir = args.output_dir.resolve()
    return args


def main(argv=None):
    args = parse_args(argv)
    if not hasattr(os, "wait4"):
        raise BenchmarkError("This harness requires Unix os.wait4")
    counter, counter_method = make_thread_counter()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "status": "running",
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host": host_metadata(),
        "configuration": {"repetitions": args.repetitions, "warmups": args.warmups,
                          "seed": args.seed, "extra_args": args.extra_arg,
                          "stringtie_p_argument": 1,
                          "thread_counter": counter_method,
                          "normalization": "remove only lines starting with #; "
                                           "preserve all other bytes and order",
                          "schedule": "seeded random first label, then alternate "
                                      "first label for successive paired repetitions",
                          "timing": "perf_counter around spawn through wait4; "
                                    "hashing excluded; warmups/probes excluded",
                          "thread_verification_scope": "separate untimed runs; "
                                    "sampling cannot exclude threads shorter than the "
                                    "sampling interval; use audited NOTHREADS builds"},
        "files": {}, "runs": [],
    }
    paths = {"baseline": args.baseline, "candidate": args.candidate, "input": args.input}
    expected = None
    rng = random.Random(args.seed)
    try:
        for label, path in paths.items():
            report["files"][label] = {"path": str(path), "size_bytes": path.stat().st_size,
                                      "sha256": file_sha256(path)}
        save_report(args.output_dir, report)
        # Probes run first so resource violations fail before timing the comparison.
        phases = [("thread_probe", 1), ("warmup", args.warmups),
                  ("measurement", args.repetitions)]
        for phase, count in phases:
            first = rng.randrange(2)
            for repetition in range(count):
                labels = ["baseline", "candidate"]
                if (first + repetition) % 2:
                    labels.reverse()
                for label in labels:
                    run_id = f"{phase}-{repetition + 1:02d}"
                    print(f"{run_id}: {label}", flush=True)
                    run = run_once(label, paths[label], args.input, args.output_dir,
                                   run_id, args.extra_arg,
                                   counter if phase == "thread_probe" else None)
                    run.update({"phase": phase, "repetition": repetition + 1,
                                "global_order": len(report["runs"]) + 1})
                    report["runs"].append(run)
                    expected = validate_run(run, expected)
                    report["expected_normalized_gtf_sha256"] = expected
                    save_report(args.output_dir, report)
                    if phase == "measurement":
                        print(f"  {run['wall_seconds']:.6f} s wall; "
                              f"{run['cpu_seconds']:.6f} s CPU; GTF PASS", flush=True)
        for label, path in paths.items():
            if file_sha256(path) != report["files"][label]["sha256"]:
                raise BenchmarkError(f"{label} changed during benchmarking: {path}")
        report["summary"] = summarize(report["runs"])
        report["status"] = "pass"
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_report(args.output_dir, report)
    summary = report["summary"]
    print(f"\nBaseline median: {summary['baseline']['wall_seconds']['median']:.6f} s")
    print(f"Candidate median: {summary['candidate']['wall_seconds']['median']:.6f} s")
    print(f"Speedup (ratio of medians): {summary['wall_speedup_ratio_of_medians']:.3f}x")
    print(f"Time saved: {summary['wall_time_reduction_percent']:.2f}%")
    print("One-thread probes: PASS; all normalized GTFs identical")
    print(f"Report: {args.output_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
