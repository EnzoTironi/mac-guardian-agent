#!/usr/bin/env python3
"""Check the built image and isolated Plow probe without credentials or a Mac."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid


def verify(image, platform=None):
    results = []
    tests = Path(__file__).resolve().parents[1] / "tests/runtime"
    for kind in ("runtime-contract", "plow-boot-probe"):
        name = "mac-guardian-probe-" + uuid.uuid4().hex
        command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--no-healthcheck"]
        if platform:
            command += ["--platform", platform]
        if kind == "runtime-contract":
            command += ["--mount", f"type=bind,source={tests},target=/tmp/guardian-tests,readonly",
                        "--entrypoint", "node", image, "--test", "/tmp/guardian-tests/*.test.mjs"]
        else:
            command += ["--entrypoint", "/opt/plow/probe", image]
        started = time.monotonic()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=150)
            output = result.stdout + result.stderr
            ok = result.returncode == 0 and (kind != "plow-boot-probe" or "PLOW_PROBE_OK" in output)
            item = {"check": kind, "ok": ok, "exit_code": result.returncode,
                    "elapsed_seconds": round(time.monotonic() - started, 2)}
            if kind == "plow-boot-probe":
                item["ready_marker"] = "PLOW_PROBE_OK" in output
            if not ok:
                item["output"] = output[-8000:]
            results.append(item)
        except subprocess.TimeoutExpired:
            results.append({"check": kind, "ok": False, "error": "timeout"})
        finally:
            # Only the disposable, credential-free container created above.
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=30)
    return {"image": image, "platform": platform, "ok": all(r["ok"] for r in results),
            "scope": "isolated-fixture-no-mac-no-delivery", "checks": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--platform", choices=["linux/amd64", "linux/arm64"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.image, args.platform)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized, end="")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
