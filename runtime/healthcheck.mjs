// Check the running gateway without loading config or touching the state lock.
import { pathToFileURL } from "node:url";

export async function gatewayReady(url = "http://127.0.0.1:3000/readyz") {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(5000), redirect: "error" });
    if (!response.ok) return false;
    const status = await response.json();
    return status.ready === true && Array.isArray(status.failing) && status.failing.length === 0;
  } catch {
    return false;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const ready = await gatewayReady();
  console.log(ready ? "mac-guardian: gateway ready" : "mac-guardian: gateway unavailable");
  process.exitCode = ready ? 0 : 1;
}
