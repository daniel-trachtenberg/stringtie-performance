#!/usr/bin/env python3
"""Test-only stand-in: writes a tiny GTF and optionally violates a requirement."""
import os
from pathlib import Path
import sys
import threading
import time

if "--fake-threads" in sys.argv:
    worker = threading.Thread(target=lambda: time.sleep(0.15))
    worker.start()
time.sleep(0.08)
if "--fake-nonzero" in sys.argv:
    sys.exit(3)
output = Path(sys.argv[sys.argv.index("-o") + 1])
if "--fake-empty" not in sys.argv:
    output.write_text(f"# invocation pid {os.getpid()}\n"
                      "chr1\tmock\ttranscript\t1\t10\t.\t+\t.\tgene_id \"g1\";\n")
if "--fake-threads" in sys.argv:
    worker.join()
