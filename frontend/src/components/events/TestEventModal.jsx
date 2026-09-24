import React, { useState } from 'react';
import { X, Play, Loader2, Sparkles, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import api from '../../services/api';

const PRESET_ERRORS = [
  {
    name: 'Database Timeout Error',
    exception_type: 'DatabaseConnectionTimeout',
    message: 'Connection to primary replica timed out after 3000ms',
    stack_trace: 'Traceback (most recent call last):\n  File "services/db/pool.py", line 88, in acquire_conn\nTimeoutError: connection timed out',
    release: '1.2.0',
  },
  {
    name: 'Zero Division Error',
    exception_type: 'ZeroDivisionError',
    message: 'division by zero during metric calculation',
    stack_trace: 'Traceback (most recent call last):\n  File "analytics/calc.py", line 42, in compute_rate\nZeroDivisionError: division by zero',
    release: '1.2.0',
  },
  {
    name: 'Key Not Found Error',
    exception_type: 'KeyError',
    message: "'tenant_id' key missing from authorization payload",
    stack_trace: 'Traceback (most recent call last):\n  File "middleware/auth.py", line 19, in verify_token\nKeyError: \'tenant_id\'',
    release: '1.1.9',
  },
];

export function TestEventModal({ isOpen, onClose, onEventSent }) {
  const { selectedProject } = useProject();
  const [selectedPreset, setSelectedPreset] = useState(0);
  const [exceptionType, setExceptionType] = useState(PRESET_ERRORS[0].exception_type);
  const [message, setMessage] = useState(PRESET_ERRORS[0].message);
  const [stackTrace, setStackTrace] = useState(PRESET_ERRORS[0].stack_trace);
  const [release, setRelease] = useState(PRESET_ERRORS[0].release);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleSelectPreset = (index) => {
    setSelectedPreset(index);
    const p = PRESET_ERRORS[index];
    setExceptionType(p.exception_type);
    setMessage(p.message);
    setStackTrace(p.stack_trace);
    setRelease(p.release);
    setResult(null);
    setError(null);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!selectedProject) return;

    setIsSubmitting(true);
    setResult(null);
    setError(null);

    try {
      const res = await api.ingestEvent(selectedProject.id, {
        exception_type: exceptionType,
        message,
        stack_trace: stackTrace,
        release: release || null,
      });
      setResult(res);
      if (onEventSent) onEventSent(res);
    } catch (err) {
      setError(err.message || 'Failed to ingest event');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 overflow-y-auto">
      <div className="w-full max-w-lg bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden my-8">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-amber-500/10 text-amber-400">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-100">Simulate Error Ingestion</h3>
              <p className="text-[11px] text-zinc-400">
                Trigger an error event into project <span className="text-zinc-200 font-semibold">{selectedProject?.name}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 p-1 rounded-md transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Preset Buttons */}
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-2">Preset Error Scenarios</label>
            <div className="grid grid-cols-3 gap-2">
              {PRESET_ERRORS.map((preset, idx) => (
                <button
                  key={preset.name}
                  type="button"
                  onClick={() => handleSelectPreset(idx)}
                  className={`px-2.5 py-1.5 rounded-lg text-left text-xs border transition ${
                    selectedPreset === idx
                      ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-300 font-medium'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-400 hover:border-zinc-700'
                  }`}
                >
                  <div className="truncate font-semibold">{preset.name}</div>
                  <div className="text-[10px] text-zinc-400 truncate font-mono">{preset.exception_type}</div>
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSend} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Exception Type</label>
              <input
                type="text"
                required
                value={exceptionType}
                onChange={(e) => setExceptionType(e.target.value)}
                className="w-full px-3 py-1.5 text-xs font-mono bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Message</label>
              <input
                type="text"
                required
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="w-full px-3 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Stack Trace</label>
              <textarea
                rows={3}
                required
                value={stackTrace}
                onChange={(e) => setStackTrace(e.target.value)}
                className="w-full px-3 py-1.5 text-xs font-mono bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Release (optional)</label>
              <input
                type="text"
                value={release}
                onChange={(e) => setRelease(e.target.value)}
                placeholder="e.g. 1.2.0"
                className="w-full px-3 py-1.5 text-xs font-mono bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 focus:outline-none focus:border-indigo-500"
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                <span>{error}</span>
              </div>
            )}

            {result && (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 space-y-1">
                <div className="flex items-center gap-1.5 font-semibold text-emerald-200">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span>
                    {result.created_new_issue
                      ? 'New Issue Created!'
                      : 'Existing Issue Incremented!'}
                  </span>
                </div>
                <div className="text-[11px] text-zinc-400 font-mono">
                  Issue ID: #{result.issue_id} • Total Occurrences: {result.issue_count} • Event ID: #{result.event_id}
                </div>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition"
              >
                Close
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !selectedProject}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition"
              >
                {isSubmitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                Fire Event
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default TestEventModal;
