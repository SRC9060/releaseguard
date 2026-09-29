/**
 * Formatting helpers for timestamps, numbers, and fingerprints
 */

/**
 * Safely parses any date string into a Date object representing an exact UTC instant.
 * If an ISO-8601 string lacks a timezone designator, appends 'Z' so browsers do NOT
 * incorrectly interpret the UTC time as local time.
 */
export function parseUtcDate(dateString) {
  if (!dateString) return null;
  if (dateString instanceof Date) return dateString;
  let str = String(dateString).trim();
  if (str.includes('T') && !str.endsWith('Z') && !/[+-]\d{2}(:?\d{2})?$/.test(str)) {
    str += 'Z';
  }
  const parsed = new Date(str);
  return isNaN(parsed.getTime()) ? null : parsed;
}

export function formatRelativeTime(dateString) {
  if (!dateString) return 'Never';
  const date = parseUtcDate(dateString);
  if (!date) return 'Never';
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 5) return 'just now';
  if (diffInSeconds < 60) return `${diffInSeconds}s ago`;

  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) return `${diffInMinutes}m ago`;

  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) return `${diffInHours}h ago`;

  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 30) return `${diffInDays}d ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatExactTimestamp(dateString, options = {}) {
  if (!dateString) return '-';
  const date = parseUtcDate(dateString);
  if (!date) return '-';
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZoneName: 'short',
    ...options,
  });
}

export function formatFingerprint(fp, length = 12) {
  if (!fp) return '-';
  if (fp.length <= length) return fp;
  return `${fp.slice(0, length)}...`;
}

export function formatNumber(num) {
  if (num === undefined || num === null) return '0';
  return new Intl.NumberFormat('en-US').format(num);
}
