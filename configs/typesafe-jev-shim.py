#!/usr/bin/env python3
"""TypeSafe Jev serving recipe: the typesafe backend of the s1 gateway.

The measured `system1` baseline (results/2026-09-30/typesafe-jev-1-13-s1.json,
REPORT-jev-s1.md) was produced through this endpoint. Today it is one backend
of the standard s1 gateway — this launcher pins `S1_BACKEND=typesafe` and
starts it, so "the Jev endpoint" keeps a name of its own.

Run:  TYPESAFE_API_KEY=... python3 configs/typesafe-jev-shim.py
Then: BENCH_BASE_URL=http://localhost:8123/v1 BENCH_MODEL=jev-latest \\
      ./bench run --suite system1 --samples 2 --label "typesafe-jev s1"

See docs/S1-ENDPOINT.md for the contract and configs/s1_gateway.py for the
backend machinery (proxy, laya stub).
"""
import os
import runpy

os.environ.setdefault("S1_BACKEND", "typesafe")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "s1_gateway.py"), run_name="__main__")
