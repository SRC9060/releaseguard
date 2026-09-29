import test from 'node:test';
import assert from 'node:assert/strict';
import { parseUtcDate, formatRelativeTime, formatExactTimestamp } from './formatters.js';

test('parseUtcDate: parses ISO strings with Z as UTC instant', () => {
  const dt = parseUtcDate('2026-09-28T18:44:31Z');
  assert.equal(dt.getTime(), 1790621071000);
  assert.equal(dt.getUTCFullYear(), 2026);
  assert.equal(dt.getUTCMonth(), 8); // 0-indexed September
  assert.equal(dt.getUTCDate(), 28);
  assert.equal(dt.getUTCHours(), 18);
  assert.equal(dt.getUTCMinutes(), 44);
  assert.equal(dt.getUTCSeconds(), 31);
});

test('parseUtcDate: parses naive ISO strings as UTC without local time distortion', () => {
  const dt = parseUtcDate('2026-09-28T18:44:31');
  assert.equal(dt.getTime(), 1790621071000);
});

test('formatExactTimestamp: correctly formats UTC timestamp into India local time (GMT+5:30)', () => {
  // 18:44:31 UTC corresponds to 00:14:31 on the next calendar day in India (GMT+5:30)
  const result = formatExactTimestamp('2026-09-28T18:44:31Z', { timeZone: 'Asia/Kolkata' });
  assert.ok(result.includes('Sep 29, 2026'), `Expected Sep 29, 2026, got ${result}`);
  assert.ok(result.includes('00:14:31'), `Expected 00:14:31, got ${result}`);
  assert.ok(result.includes('GMT+5:30'), `Expected GMT+5:30, got ${result}`);
});

test('formatRelativeTime: calculates difference against actual instant', () => {
  const now = new Date();
  const justNowIso = new Date(now.getTime() - 2000).toISOString();
  assert.equal(formatRelativeTime(justNowIso), 'just now');

  const tenSecAgoIso = new Date(now.getTime() - 10000).toISOString();
  assert.equal(formatRelativeTime(tenSecAgoIso), '10s ago');

  const fiveMinAgoIso = new Date(now.getTime() - 300000).toISOString();
  assert.equal(formatRelativeTime(fiveMinAgoIso), '5m ago');
});
