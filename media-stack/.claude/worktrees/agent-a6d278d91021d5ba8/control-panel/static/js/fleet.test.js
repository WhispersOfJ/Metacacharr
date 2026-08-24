import { test } from "node:test";
import assert from "node:assert/strict";
import { groupHistoryFor } from "./fleet.js";

test("groupHistoryFor returns the same buffer object across calls for the same name", () => {
  const a = groupHistoryFor("radarr");
  const b = groupHistoryFor("radarr");
  assert.equal(a, b);
});

test("groupHistoryFor returns distinct buffers for distinct names", () => {
  const a = groupHistoryFor("radarr");
  const b = groupHistoryFor("sonarr");
  assert.notEqual(a, b);
});
