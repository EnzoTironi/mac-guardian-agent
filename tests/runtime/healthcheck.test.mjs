import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";
import { gatewayReady } from "/opt/mac-guardian/runtime/healthcheck.mjs";

const cases = [
  { name: "ready gateway", code: 200, body: { ready: true, failing: [] }, expected: true },
  { name: "live but not ready", code: 200, body: { ok: true, status: "live" }, expected: false },
  { name: "failed subsystem", code: 200, body: { ready: true, failing: ["channel"] }, expected: false },
  { name: "parked gateway", code: 503, body: { ready: false, failing: ["boot"] }, expected: false },
  { name: "invalid response", code: 200, body: "invalid JSON", expected: false },
];
for (const c of cases) test(`readiness rejects partial startup: ${c.name}`, async () => {
  const server = createServer((_req, res) => {
    res.writeHead(c.code, { "Content-Type": "application/json" });
    res.end(typeof c.body === "string" ? c.body : JSON.stringify(c.body));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    assert.equal(await gatewayReady(`http://127.0.0.1:${server.address().port}/readyz`), c.expected);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

test("a missing gateway fails instead of treating an alive container as healthy", async () => {
  assert.equal(await gatewayReady("http://127.0.0.1:1/readyz"), false);
});
