import test from "node:test";
import assert from "node:assert/strict";

test("shared config policy distinguishes writes, reads and adjacent directories", async () => {
  const { bashWritesTo } = await import("../core/config-policy.mjs");
  assert.equal(
    bashWritesTo(
      "echo hi > /tmp/native/config.json",
      "/tmp/native",
      "/home/test",
    ),
    true,
  );
  assert.equal(
    bashWritesTo(
      "cat /tmp/native/config.json 2>/dev/null",
      "/tmp/native",
      "/home/test",
    ),
    false,
  );
  assert.equal(
    bashWritesTo(
      "tee /tmp/native-other/x",
      "/tmp/native",
      "/home/test",
    ),
    false,
  );
});
