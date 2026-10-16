// The built image's contract. These run inside the image (scripts/test_image.py
// mounts this folder there); in a checkout they are skipped, not passed.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const inImage = existsSync("/opt/plow/boot/config.js");
const skip = inImage ? false : "runs inside the built image only (python3 scripts/test_image.py IMAGE)";
const identity = { agent: { name: "Mac Guardian" }, line: { uid: "fixture-line" }, chats: [], mcp_url: "http://fixture.invalid" };

test("the actual compiled base isolates the owner's Mac and grants no guest tools", { skip }, async () => {
  const { renderConfig } = await import("/opt/plow/boot/config.js");
  const config = renderConfig(identity, "http://fixture.invalid");
  assert.equal(config.channels.plow.threadTrust, "untrusted");
  assert.deepEqual(config.channels.plow.guestTools, []);
  assert.equal(config.bindings[0].match.peer.id, "plow-owner");
  assert.equal(config.session.groupScope, "per-group");
  assert.equal(config.tools.message.crossContext.allowWithinProvider, false);
  assert.equal(config.memory.search.rememberAcrossConversations, false);
});

test("the image has its listing identity, complete native worker and official reporter", { skip }, () => {
  assert.match(process.env.AGENT_ID, /^[a-z0-9][a-z0-9-]{1,63}$/);
  assert.deepEqual(readdirSync("/opt/mac-guardian").sort(), ["attention.py", "install_native.py", "mac_guardian.py", "runtime", "workspace_care.py"]);
  const home = mkdtempSync(join(tmpdir(), "guardian-native-fixture-"));
  try {
    const result = JSON.parse(execFileSync("python3", ["/opt/mac-guardian/mac_guardian.py", "--home", home, "setup-status"], { encoding: "utf8", timeout: 20_000 }));
    assert.equal(result.scope, "native-mac");
    assert.equal(result.care_ready, false);
    assert.equal(result.next, "connect-real-mac");
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
  const boot = readFileSync("/opt/plow/boot/main.js", "utf8");
  assert.match(boot, /startAgentIndex\(300_000, writeLog\)/);
  assert.match(boot, /startGateway\(false/);
  assert.ok(readFileSync("/opt/plow/agent-index-client.py", "utf8").length > 1000);
});

test("the install command pins this image's own native files", { skip }, async () => {
  const generator = await import("/opt/plow/skills/mac-health/scripts/install-command.mjs");
  if (!/^[a-f0-9]{40}$/.test(process.env.MAC_GUARDIAN_REVISION ?? "")) {
    assert.throws(() => generator.command("install", { python: "/opt/homebrew/bin/python3" }), /release_not_pinned/);
    return;
  }
  const args = generator.command("install", { python: "/opt/homebrew/bin/python3" });
  const pinned = JSON.parse(args.argv[5]);
  for (const [rel, name] of Object.entries(generator.FILES)) {
    assert.equal(pinned[rel], createHash("sha256").update(readFileSync(join("/opt/mac-guardian", name))).digest("hex"));
  }
  assert.ok(args.argv[4].endsWith(`/${process.env.MAC_GUARDIAN_REVISION}/`));
});

test("native setup evidence and consent are requested before old conversation assumptions", { skip }, () => {
  const prompt = readFileSync("/opt/plow/prompt/AGENTS.md", "utf8");
  const skill = readFileSync("/opt/plow/skills/mac-health/SKILL.md", "utf8");
  assert.match(prompt, /setup-status/);
  assert.match(skill, /setup-status/);
  assert.match(skill, /consent --scope organize --grant/);
});
