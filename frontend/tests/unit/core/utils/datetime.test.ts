import { expect, test, vi } from "vitest";

import { formatTimeAgo, normalizeDateInput } from "@/core/utils/datetime";

test("normalizes timezone-less ISO timestamps as UTC", () => {
  expect(normalizeDateInput("2026-04-30T03:12:19").toISOString()).toBe(
    "2026-04-30T03:12:19.000Z",
  );
});

test("keeps explicit UTC timestamps unchanged", () => {
  expect(normalizeDateInput("2026-04-30T03:12:19Z").toISOString()).toBe(
    "2026-04-30T03:12:19.000Z",
  );
});

test("normalizes unix-second timestamps", () => {
  expect(normalizeDateInput("1714446739").toISOString()).toBe(
    "2024-04-30T03:12:19.000Z",
  );
});

test("formatTimeAgo uses normalized UTC parsing for timezone-less ISO strings", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-04-30T03:42:19.000Z"));

  expect(formatTimeAgo("2026-04-30T03:12:19", "en-US")).toContain(
    "30 minutes ago",
  );

  vi.useRealTimers();
});
