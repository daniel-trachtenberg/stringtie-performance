import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import benchmark_serial as bench


class HarnessTests(unittest.TestCase):
    def test_hash_ignores_comments_but_preserves_order_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, c, d = [root / name for name in "abcd"]
            a.write_bytes(b"# original header\na\nb\n")
            b.write_bytes(b"# other header\na\nb\n")
            c.write_bytes(b"b\na\n")
            d.write_bytes(b"a\nb")
            hash_a = bench.gtf_fingerprint(a)["sha256"]
            self.assertEqual(hash_a, bench.gtf_fingerprint(b)["sha256"])
            self.assertNotEqual(hash_a, bench.gtf_fingerprint(c)["sha256"])
            self.assertNotEqual(hash_a, bench.gtf_fingerprint(d)["sha256"])

    def test_empty_and_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.gtf"
            path.write_bytes(b"# comment\n\n")
            with self.assertRaises(bench.BenchmarkError):
                bench.gtf_fingerprint(path)
            path.write_bytes(b"actual row\n")
            record = {"exit_code": 0, "output": str(path),
                      "run_id": "test", "label": "candidate"}
            with self.assertRaises(bench.BenchmarkError):
                bench.validate_run(record, "incorrect hash")

    def run_mock(self, extra=()):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "report"
        fixture = Path(__file__).with_name("mock_stringtie.py")
        args = ["--baseline", str(fixture), "--candidate", str(fixture),
                "--input", str(fixture), "--output-dir", str(output),
                "--repetitions", "2", "--warmups", "0"]
        args.extend("--extra-arg=" + arg for arg in extra)
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                bench.main(args)
            except bench.BenchmarkError as error:
                return output, error
        return output, None

    def test_integration_pass_resources_and_schedule(self):
        output, error = self.run_mock()
        self.assertIsNone(error)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(report["runs"]), 6)  # 2 probes + 2 pairs
        measured = [run for run in report["runs"] if run["phase"] == "measurement"]
        self.assertNotEqual(measured[0]["label"], measured[2]["label"])
        for run in report["runs"]:
            self.assertGreater(run["peak_rss_bytes"], 0)
            self.assertGreater(run["wall_seconds"], 0)
            self.assertEqual(run["correctness"], "pass")
        for label in ("baseline", "candidate", "input"):
            self.assertEqual(len(report["files"][label]["sha256"]), 64)

    def test_extra_threads_fail_and_save_evidence(self):
        output, error = self.run_mock(["--fake-threads"])
        self.assertIsNotNone(error)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertGreater(report["runs"][0]["thread_probe"]["maximum_observed"], 1)

    def test_nonzero_exit_and_missing_output_fail(self):
        for option in ("--fake-nonzero", "--fake-empty"):
            with self.subTest(option=option):
                output, error = self.run_mock([option])
                self.assertIsNotNone(error)
                report = json.loads((output / "report.json").read_text())
                self.assertEqual(report["status"], "failed")

    def test_existing_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test-candidate.gtf").write_bytes(b"stale output\n")
            with self.assertRaises(bench.BenchmarkError):
                bench.run_once("candidate", Path("/does/not/exist"),
                               Path("/does/not/exist"), root, "test", [])


if __name__ == "__main__":
    unittest.main()
