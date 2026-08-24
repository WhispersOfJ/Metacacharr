import { test } from "node:test";
import assert from "node:assert/strict";
import { formatLogLine, formatLogText } from "./core.js";

test("formatLogLine reformats a docker RFC3339Nano timestamp to local clock", () => {
  const line = "2026-08-19T10:30:00.123456789Z hello world";
  const result = formatLogLine(line);
  assert.match(result, /^\[\d{2}:\d{2}:\d{2}\] hello world$/);
});

test("formatLogLine passes through lines with no timestamp prefix unchanged", () => {
  assert.equal(formatLogLine("no timestamp here"), "no timestamp here");
});

test("formatLogLine handles a timestamp with no fractional seconds", () => {
  const line = "2026-08-19T10:30:00Z plain";
  const result = formatLogLine(line);
  assert.match(result, /^\[\d{2}:\d{2}:\d{2}\] plain$/);
});

test("formatLogText reformats every line independently", () => {
  const raw = "2026-08-19T10:30:00Z first\nno-prefix second\n2026-08-19T10:30:01Z third";
  const result = formatLogText(raw);
  const lines = result.split("\n");
  assert.equal(lines.length, 3);
  assert.match(lines[0], /^\[\d{2}:\d{2}:\d{2}\] first$/);
  assert.equal(lines[1], "no-prefix second");
  assert.match(lines[2], /^\[\d{2}:\d{2}:\d{2}\] third$/);
});
