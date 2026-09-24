import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import AppShell from './components/layout/AppShell';
import OverviewPage from './pages/OverviewPage';
import IssuesPage from './pages/IssuesPage';
import IssueDetailPage from './pages/IssueDetailPage';
import ComingSoonPage from './pages/ComingSoonPage';

function App() {
  const [eventTriggerKey, setEventTriggerKey] = useState(0);

  const handleEventIngested = () => {
    // Increment to trigger refetches in child pages if needed
    setEventTriggerKey((k) => k + 1);
  };

  return (
    <ProjectProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell onEventIngested={handleEventIngested} />}>
            <Route path="/" element={<OverviewPage key={eventTriggerKey} />} />
            <Route path="/overview" element={<Navigate to="/" replace />} />
            <Route path="/issues" element={<IssuesPage key={eventTriggerKey} />} />
            <Route path="/issues/:id" element={<IssueDetailPage />} />

            {/* Coming Soon Sections */}
            <Route
              path="/releases"
              element={
                <ComingSoonPage
                  title="Release Tracking"
                  description="Track production deploy regressions, compare error velocity across git commits, and monitor release health."
                  roadmapVersion="v0.2"
                />
              }
            />
            <Route
              path="/feature-flags"
              element={
                <ComingSoonPage
                  title="Deterministic Feature Flags"
                  description="Safely roll out features with automatic kill-switches tied directly to real-time error rate thresholds."
                  roadmapVersion="v0.2"
                />
              }
            />
            <Route
              path="/incidents"
              element={
                <ComingSoonPage
                  title="Incident Management"
                  description="Correlate active error surges into actionable incidents with automated PagerDuty / Slack notifications."
                  roadmapVersion="v0.3"
                />
              }
            />
            <Route
              path="/projects"
              element={
                <ComingSoonPage
                  title="Project Management"
                  description="Manage API ingest keys, team access permissions, and data retention rules across your organizations."
                  roadmapVersion="v0.2"
                />
              }
            />
            <Route
              path="/settings"
              element={
                <ComingSoonPage
                  title="Settings & Integrations"
                  description="Configure webhook integrations, alerts, security policies, and environment definitions."
                  roadmapVersion="v0.2"
                />
              }
            />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ProjectProvider>
  );
}

export default App;
