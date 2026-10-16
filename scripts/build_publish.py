#!/usr/bin/env python3
"""Build with listing identity; push using Plow's official CLI when requested."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image")
parser.add_argument("--platform", default="linux/amd64", choices=["linux/amd64", "linux/arm64"])
parser.add_argument("--push", action="store_true")
parser.add_argument("--promote", action="store_true")
args = parser.parse_args()
if not re.fullmatch(r"ghcr.io/[a-z0-9._-]+/[a-z0-9._-]+:[a-zA-Z0-9._-]+", args.image):
    parser.error("use ghcr.io/owner/repository:tag")
root = Path(__file__).resolve().parents[1]
listing_path = root / "listing.json"
if not listing_path.exists():
    parser.error("run configure_listing.py with the identity the owner chose")
listing = json.loads(listing_path.read_text())
# The Mac downloads the helper from GitHub at this commit and checks it against
# the image, so the tree must be clean and the commit already pushed.
if subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout.strip():
    parser.error("commit your changes first; the helper is installed from a pushed commit")
revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
if not subprocess.run(["git", "branch", "-r", "--contains", revision], cwd=root, capture_output=True, text=True).stdout.strip():
    parser.error(f"push {revision[:12]} first; the Mac downloads the helper from GitHub at that commit")
command = ["docker", "build", "--platform", args.platform, "--tag", args.image,
           "--build-arg", f"MAC_GUARDIAN_REVISION={revision}"]
for key, val in [("AGENT_ID", listing["slug"]), ("AGENT_NAME", listing["name"]), ("AGENT_BLURB", listing["blurb"])]:
    command += ["--build-arg", f"{key}={val}"]
subprocess.run(command + ["."], cwd=root, check=True)
if args.push or args.promote:
    subprocess.run([sys.executable, str(root / "scripts/test_image.py"), args.image,
                    "--platform", args.platform], cwd=root, check=True)
    command = ["plow-agents", "image", "push", args.image]
    if args.promote:
        command += ["--promote", listing["slug"]]
    subprocess.run(command, cwd=root, check=True)
