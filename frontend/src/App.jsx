import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProjectProvider } from './context/ProjectContext';
import AppShell from './components/layout/AppShell';
import OverviewPage from './pages/OverviewPage';
import IssuesPage from './pages/IssuesPage';
import IssueDetailPage from './pages/IssueDetailPage';
import ReleasesPage from './pages/ReleasesPage';
import FeatureFlagsPage from './pages/FeatureFlagsPage';
import ComingSoonPage from './pages/ComingSoonPage';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import { LoadingSpinner } from './components/common/LoadingState';

function ProtectedLayout({ onEventIngested }) {
  const { isAuthenticated, isLoadingAuth } = useAuth();

  if (isLoadingAuth) {
    return (
      <div className="min-h-screen bg-[#07080c] flex items-center justify-center">
        <LoadingSpinner text="Authenticating workspace session..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <ProjectProvider>
      <AppShell onEventIngested={onEventIngested} />
    </ProjectProvider>
  );
}

function PublicRoute({ children }) {
  const { isAuthenticated, isLoadingAuth } = useAuth();

  if (isLoadingAuth) {
    return (
      <div className="min-h-screen bg-[#07080c] flex items-center justify-center">
        <LoadingSpinner text="Checking session..." />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function App() {
  const [eventTriggerKey, setEventTriggerKey] = useState(0);

  const handleEventIngested = () => {
    setEventTriggerKey((k) => k + 1);
  };

  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Auth Routes */}
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
          <Route
            path="/register"
            element={
              <PublicRoute>
                <RegisterPage />
              </PublicRoute>
            }
          />

          {/* Protected Multi-Tenant Application Shell */}
          <Route element={<ProtectedLayout onEventIngested={handleEventIngested} />}>
            <Route path="/" element={<OverviewPage key={eventTriggerKey} />} />
            <Route path="/overview" element={<Navigate to="/" replace />} />
            <Route path="/issues" element={<IssuesPage key={eventTriggerKey} />} />
            <Route path="/issues/:id" element={<IssueDetailPage />} />

            {/* Active Releases & Feature Flags */}
            <Route path="/releases" element={<ReleasesPage />} />
            <Route path="/feature-flags" element={<FeatureFlagsPage />} />
            <Route path="/flags" element={<Navigate to="/feature-flags" replace />} />

            {/* Coming Soon Sections */}
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
    </AuthProvider>
  );
}

export default App;
