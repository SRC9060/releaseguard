import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from './AuthContext';

const ProjectContext = createContext(null);
const STORAGE_KEY = 'releaseguard_active_project_id';

export function ProjectProvider({ children }) {
  const { selectedTenant, isAuthenticated } = useAuth();
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadProjects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      let data = [];
      if (selectedTenant) {
        data = await api.getTenantProjects(selectedTenant.id);
      } else if (!isAuthenticated) {
        data = await api.getProjects();
      }
      setProjects(data);

      if (data.length > 0) {
        const saved = Number(localStorage.getItem(STORAGE_KEY));
        const match = data.find((p) => p.id === saved) || data[0];
        setSelectedProjectId(match.id);
        setSelectedProject(match);
        localStorage.setItem(STORAGE_KEY, match.id.toString());
      } else {
        setSelectedProjectId(null);
        setSelectedProject(null);
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
      setError(err.message || 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  }, [selectedTenant?.id, isAuthenticated]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const selectProject = useCallback(
    (projectOrId) => {
      const id = typeof projectOrId === 'object' ? projectOrId.id : Number(projectOrId);
      const match = projects.find((p) => p.id === id);
      if (match) {
        setSelectedProjectId(match.id);
        setSelectedProject(match);
        localStorage.setItem(STORAGE_KEY, match.id.toString());
      }
    },
    [projects]
  );

  const createProject = useCallback(
    async (name) => {
      let created = null;
      if (selectedTenant) {
        created = await api.createTenantProject(selectedTenant.id, name);
      } else {
        created = await api.createProject(name);
      }
      setProjects((prev) => [...prev, created]);
      setSelectedProjectId(created.id);
      setSelectedProject(created);
      localStorage.setItem(STORAGE_KEY, created.id.toString());
      return created;
    },
    [selectedTenant?.id]
  );

  const value = {
    projects,
    selectedProject,
    selectedProjectId,
    isLoading,
    error,
    selectProject,
    createProject,
    refreshProjects: loadProjects,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProject must be used within a ProjectProvider');
  }
  return context;
}

export default ProjectContext;
