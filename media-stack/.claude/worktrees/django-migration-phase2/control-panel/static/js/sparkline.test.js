import { test } from "node:test";
import assert from "node:assert/strict";
import { pushHistory } from "./sparkline.js";

test("pushHistory appends and caps buffer length", () => {
  const buf = [1, 2, 3];
  pushHistory(buf, 4, 3);
  assert.deepEqual(buf, [2, 3, 4]);
});

test("pushHistory does not trim under the cap", () => {
  const buf = [1, 2];
  pushHistory(buf, 3, 5);
  assert.deepEqual(buf, [1, 2, 3]);
});
