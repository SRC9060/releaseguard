import test from 'node:test';
import assert from 'node:assert/strict';

function formatDuration(startedAt, resolvedAt) {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = resolvedAt ? new Date(resolvedAt).getTime() : Date.now();
  const diffSec = Math.max(0, Math.floor((end - start) / 1000));
  const hours = Math.floor(diffSec / 3600);
  const minutes = Math.floor((diffSec % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function filterIncidents(incidents, { status, severity, environment }) {
  return incidents.filter((inc) => {
    if (status && inc.status !== status) return false;
    if (severity && inc.severity !== severity) return false;
    if (environment && inc.environment !== environment) return false;
    return true;
  });
}

function calculatePreMitigationRestore(mitigation) {
  if (!mitigation.previous_state) return null;
  return {
    enabled: mitigation.previous_state.enabled ?? true,
    rollout: mitigation.previous_state.rollout_percentage ?? 100,
  };
}

test('formatDuration: computes formatted duration for resolved incident', () => {
  const started = '2026-09-29T10:00:00Z';
  const resolved = '2026-09-29T11:45:00Z';
  assert.equal(formatDuration(started, resolved), '1h 45m');
});

test('formatDuration: computes sub-hour minutes duration', () => {
  const started = '2026-09-29T10:00:00Z';
  const resolved = '2026-09-29T10:24:00Z';
  assert.equal(formatDuration(started, resolved), '24m');
});

test('filterIncidents: filters by status and severity accurately', () => {
  const sample = [
    { id: 1, status: 'open', severity: 'critical', environment: 'production' },
    { id: 2, status: 'monitoring', severity: 'high', environment: 'production' },
    { id: 3, status: 'resolved', severity: 'critical', environment: 'staging' },
  ];

  const criticalOnly = filterIncidents(sample, { severity: 'critical' });
  assert.equal(criticalOnly.length, 2);

  const openCritical = filterIncidents(sample, { status: 'open', severity: 'critical' });
  assert.equal(openCritical.length, 1);
  assert.equal(openCritical[0].id, 1);

  const stagingOnly = filterIncidents(sample, { environment: 'staging' });
  assert.equal(stagingOnly.length, 1);
  assert.equal(stagingOnly[0].id, 3);
});

test('calculatePreMitigationRestore: accurately parses pre-mitigation snapshot', () => {
  const mit = {
    id: 10,
    previous_state: {
      enabled: true,
      rollout_percentage: 75,
    },
  };
  const restored = calculatePreMitigationRestore(mit);
  assert.deepEqual(restored, { enabled: true, rollout: 75 });
});
