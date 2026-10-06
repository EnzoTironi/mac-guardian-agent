#!/usr/bin/env python3
"""Install automatic Mac maintenance and launchd jobs. Does not install Docker or Plow."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--uninstall", action="store_true", help="Remove jobs; preserve reports, wiki and code")
args = parser.parse_args()
if sys.platform != "darwin":
    sys.exit("Este componente exige macOS.")
project = Path(__file__).resolve().parents[1]
home = Path.home()
app = home / "Library/Application Support/MacGuardian"
agents = home / "Library/LaunchAgents"
labels = ["local.macguardian.monitor", "local.macguardian.audit"]
domain = f"gui/{os.getuid()}"
if args.uninstall:
    for label in labels:
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
        (agents / (label + ".plist")).unlink(missing_ok=True)
    print("Rotinas removidas. Dados preservados.")
    sys.exit(0)
app.mkdir(parents=True, exist_ok=True, mode=0o700)
app.chmod(0o700)
logs = app / "logs"
logs.mkdir(exist_ok=True, mode=0o700)
helper = app / "mac_guardian.py"
for label in labels:
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
if helper.exists():
    shutil.copy2(helper, app / "mac_guardian.previous.py")
modules = sorted((project / "native").glob("*.py"), key=lambda module: module.name == helper.name)
for module in modules:
    temporary = app / (module.name + ".installing")
    shutil.copy2(module, temporary)
    temporary.chmod(0o700)
    temporary.replace(app / module.name)
agents.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, str(helper), "init"], check=True)
for label in labels:
    full = label.endswith("audit")
    job = {"Label": label,
           "ProgramArguments": [sys.executable, str(helper), "check", "--full"] if full else
                               [sys.executable, str(helper), "maintain"],
           "WorkingDirectory": str(app),
           "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                                    "HOMEBREW_NO_AUTO_UPDATE": "1"},
           "ProcessType": "Background",
           "LowPriorityIO": True,
           "Nice": 10,
           "StandardOutPath": str(logs / (label + ".out.log")),
           "StandardErrorPath": str(logs / (label + ".err.log"))}
    if full:
        job["StartCalendarInterval"] = {"Hour": 9, "Minute": 10}
    else:
        job["StartInterval"] = 900
        job["RunAtLoad"] = True
    path = agents / (label + ".plist")
    with path.open("wb") as f:
        plistlib.dump(job, f)
    path.chmod(0o600)
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
print(json.dumps({"installed": str(helper), "jobs": labels,
                  "mode": "automatic", "wiki": str(home / "Wiki/Home.md")}, ensure_ascii=False, indent=2))
