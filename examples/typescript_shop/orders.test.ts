import assert from "node:assert/strict";
import { once } from "node:events";
import { test } from "node:test";
import { createApp } from "./app.ts";
import { validateOrder } from "./validators.ts";

test("accepts a valid quantity", () => {
  assert.equal(validateOrder(100), true);
});

test("rejects an invalid quantity", () => {
  assert.equal(validateOrder(0), false);
});

test("serves orders through Express", async (context) => {
  const server = createApp().listen(0, "127.0.0.1");
  context.after(() => {
    server.closeAllConnections();
    server.close();
  });
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const base = `http://127.0.0.1:${address.port}`;
  assert.equal((await fetch(new URL("/orders/10", base))).status, 200);
  assert.equal((await fetch(new URL("/orders/0", base))).status, 400);
});
