import { formatDistanceToNow } from "date-fns";
import { enUS as dateFnsEnUS, zhCN as dateFnsZhCN } from "date-fns/locale";

import { detectLocale, type Locale } from "@/core/i18n";
import { getLocaleFromCookie } from "@/core/i18n/cookies";

const UNIX_SECONDS_RE = /^\d{10}(?:\.\d+)?$/;
const UNIX_MILLISECONDS_RE = /^\d{13}$/;
const ISO_WITHOUT_TIMEZONE_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

function getDateFnsLocale(locale: Locale) {
  switch (locale) {
    case "zh-CN":
      return dateFnsZhCN;
    case "en-US":
    default:
      return dateFnsEnUS;
  }
}

export function normalizeDateInput(date: Date | string | number) {
  if (date instanceof Date) {
    return date;
  }

  if (typeof date === "number") {
    return new Date(date < 1e12 ? date * 1000 : date);
  }

  const trimmed = date.trim();

  if (UNIX_SECONDS_RE.test(trimmed)) {
    return new Date(Number.parseFloat(trimmed) * 1000);
  }

  if (UNIX_MILLISECONDS_RE.test(trimmed)) {
    return new Date(Number.parseInt(trimmed, 10));
  }

  if (ISO_WITHOUT_TIMEZONE_RE.test(trimmed)) {
    return new Date(`${trimmed}Z`);
  }

  return new Date(trimmed);
}

export function formatTimeAgo(date: Date | string | number, locale?: Locale) {
  const effectiveLocale =
    locale ??
    (getLocaleFromCookie() as Locale | null) ??
    // Fallback when cookie is missing (or on first render)
    detectLocale();
  return formatDistanceToNow(normalizeDateInput(date), {
    addSuffix: true,
    locale: getDateFnsLocale(effectiveLocale),
  });
}
