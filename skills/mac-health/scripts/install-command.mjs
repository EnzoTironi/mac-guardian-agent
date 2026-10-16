#!/usr/bin/env node
// Prints the exact plow_run_command arguments that install, update or remove the
// native helper on the owner's Mac. The agent passes the printed JSON to Latch
// unchanged; the owner approves it on the Mac.
//
// The Mac downloads the helper from GitHub at the commit this image was built
// from and refuses any file whose SHA-256 differs from the copy inside this
// image. So what runs on the Mac is byte-for-byte what was reviewed and shipped
// here, and a moved tag or a compromised download cannot substitute other code.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export const APP = "~/Library/Application Support/MacGuardian";
export const LABELS = ["local.macguardian.monitor", "local.macguardian.audit"];
// Repository path on GitHub -> file name inside this image.
export const FILES = {
  "native/attention.py": "attention.py",
  "native/mac_guardian.py": "mac_guardian.py",
  "native/workspace_care.py": "workspace_care.py",
  "scripts/install_native.py": "install_native.py",
};

// Absolute candidates only: /usr/bin/python3 is Python 3.9 on current macOS, and
// without the Command Line Tools it opens an install dialog instead of running.
export const PROBE = `home=$HOME
for p in /opt/homebrew/bin/python3 /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 "$home/.local/bin/python3" "$home/.local/bin/python3.13" "$home/.local/bin/python3.12"; do
  if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then python=$p; break; fi
done
helper="$home/Library/Application Support/MacGuardian/mac_guardian.py"
installed=false; [ -f "$helper" ] && installed=true
printf '{"home": "%s", "python": "%s", "installed": %s}\\n' "$home" "\${python:-}" "$installed"`;

// Runs on the Mac with the Python found by the probe. Standard library only and
// compatible with Python 3.9 syntax so a wrong interpreter fails with a message.
export const BOOTSTRAP = `import hashlib, json, os, shutil, subprocess, sys, tempfile
if sys.version_info < (3, 11):
    sys.exit("Mac Guardian needs Python 3.11 or newer; this is " + sys.version.split()[0])
base, files = sys.argv[1], json.loads(sys.argv[2])
if not base.startswith("https://raw.githubusercontent.com/"):
    sys.exit("refusing an unexpected download source")
app = os.path.expanduser("~/Library/Application Support/MacGuardian")
os.makedirs(app, mode=0o700, exist_ok=True)
stage = tempfile.mkdtemp(prefix="install-", dir=app)
try:
    for rel, want in sorted(files.items()):
        if rel.startswith("/") or ".." in rel.split("/"):
            sys.exit("refusing unsafe path " + rel)
        got = subprocess.run(["/usr/bin/curl", "-fsSL", "--proto", "=https", "--max-time", "60", base + rel],
                             capture_output=True)
        if got.returncode:
            sys.exit("download failed for " + rel + ": " + got.stderr.decode(errors="replace")[-300:])
        if hashlib.sha256(got.stdout).hexdigest() != want:
            sys.exit("checksum mismatch for " + rel + "; nothing was installed")
        dest = os.path.join(stage, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(got.stdout)
    sys.exit(subprocess.call([sys.executable, os.path.join(stage, "scripts", "install_native.py")]))
finally:
    shutil.rmtree(stage, ignore_errors=True)
`;

// Stops and removes the two background jobs. Wiki, reports, backups and the
// helper's state stay on the Mac.
export const UNINSTALL = `import os, subprocess
uid = os.getuid()
for label in ${JSON.stringify(LABELS)}:
    subprocess.run(["launchctl", "bootout", "gui/%d/%s" % (uid, label)], capture_output=True)
    plist = os.path.expanduser("~/Library/LaunchAgents/" + label + ".plist")
    if os.path.isfile(plist) and not os.path.islink(plist):
        os.remove(plist)
print('{"removed": ' + str(len(${JSON.stringify(LABELS)})) + ', "data_preserved": true}')
`;

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

export function manifest(dir = process.env.MAC_GUARDIAN_NATIVE_DIR ?? "/opt/mac-guardian") {
  return Object.fromEntries(Object.entries(FILES).map(([rel, name]) =>
    [rel, createHash("sha256").update(readFileSync(join(dir, name))).digest("hex")]));
}

export function release(env = process.env) {
  const revision = env.MAC_GUARDIAN_REVISION ?? "";
  const source = env.MAC_GUARDIAN_SOURCE ?? "EnzoTironi/mac-guardian-agent";
  if (!/^[a-f0-9]{40}$/.test(revision)) {
    throw new Error("release_not_pinned: this image was built without MAC_GUARDIAN_REVISION (a full commit SHA)");
  }
  if (!/^[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(source)) throw new Error("invalid MAC_GUARDIAN_SOURCE");
  return { revision, source, base: `https://raw.githubusercontent.com/${source}/${revision}/` };
}

export function python(path) {
  // An interpreter path from the probe, never a shell string.
  if (!/^\/[A-Za-z0-9._/ -]*\/python3(\.\d{1,2})?$/.test(path ?? "") || path.split("/").includes("..")) {
    throw new Error("--python must be the absolute python3 path the probe printed");
  }
  return path;
}

export function command(action, options = {}, env = process.env) {
  if (action === "probe") {
    return { argv: ["/bin/sh", "-c", PROBE], read_paths: [APP],
             goal: "Mac Guardian: find Python 3.11+ and whether the helper is installed" };
  }
  if (action === "install") {
    const { base, revision } = release(env);
    return {
      argv: [python(options.python), "-I", "-c", BOOTSTRAP, base, JSON.stringify(manifest(options.dir))],
      network: true,
      read_paths: [APP],
      write_paths: [APP, "~/Library/LaunchAgents", "~/Backup/MacGuardian"],
      goal: `Mac Guardian: install the verified helper from commit ${revision.slice(0, 12)} and its two background jobs`,
    };
  }
  if (action === "uninstall") {
    return { argv: [python(options.python), "-I", "-c", UNINSTALL], write_paths: ["~/Library/LaunchAgents"],
             goal: "Mac Guardian: stop its background jobs; files, wiki and backups stay" };
  }
  throw new Error("usage: install-command.mjs probe | install --python PATH | uninstall --python PATH");
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [action, flag, value] = process.argv.slice(2);
  try {
    if (flag !== undefined && flag !== "--python") throw new Error(`unknown option ${flag}`);
    console.log(JSON.stringify(command(action, { python: value })));
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
}
