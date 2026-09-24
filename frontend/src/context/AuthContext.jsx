import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api, { getAuthToken, setAuthToken, clearAuthToken } from '../services/api';

const AuthContext = createContext(null);
const ACTIVE_TENANT_KEY = 'releaseguard_active_tenant_id';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);

  // Initialize auth state by checking token and fetching profile
  const loadUserProfile = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      setTenants([]);
      setSelectedTenant(null);
      setIsLoadingAuth(false);
      return;
    }

    try {
      const data = await api.getMe();
      setUser({ id: data.id, email: data.email });
      setTenants(data.tenants || []);

      if (data.tenants && data.tenants.length > 0) {
        const savedTenantId = Number(localStorage.getItem(ACTIVE_TENANT_KEY));
        const matched = data.tenants.find((t) => t.id === savedTenantId) || data.tenants[0];
        setSelectedTenant(matched);
        localStorage.setItem(ACTIVE_TENANT_KEY, matched.id.toString());
      } else {
        setSelectedTenant(null);
      }
    } catch (err) {
      console.warn('Failed to restore auth session:', err.message);
      clearAuthToken();
      setUser(null);
      setTenants([]);
      setSelectedTenant(null);
    } finally {
      setIsLoadingAuth(false);
    }
  }, []);

  useEffect(() => {
    loadUserProfile();
  }, [loadUserProfile]);

  const selectTenant = useCallback(
    (tenantOrId) => {
      const id = typeof tenantOrId === 'object' ? tenantOrId.id : Number(tenantOrId);
      const match = tenants.find((t) => t.id === id);
      if (match) {
        setSelectedTenant(match);
        localStorage.setItem(ACTIVE_TENANT_KEY, match.id.toString());
      }
    },
    [tenants]
  );

  const login = useCallback(
    async (email, password) => {
      const resp = await api.login(email, password);
      setAuthToken(resp.access_token);
      await loadUserProfile();
      return resp;
    },
    [loadUserProfile]
  );

  const register = useCallback(
    async (email, password, tenantName) => {
      const resp = await api.register(email, password, tenantName);
      setAuthToken(resp.access_token);
      await loadUserProfile();
      return resp;
    },
    [loadUserProfile]
  );

  const logout = useCallback(() => {
    clearAuthToken();
    localStorage.removeItem(ACTIVE_TENANT_KEY);
    setUser(null);
    setTenants([]);
    setSelectedTenant(null);
  }, []);

  const createTenant = useCallback(
    async (name) => {
      const created = await api.createTenant(name);
      setTenants((prev) => [...prev, created]);
      setSelectedTenant(created);
      localStorage.setItem(ACTIVE_TENANT_KEY, created.id.toString());
      return created;
    },
    []
  );

  const value = {
    user,
    tenants,
    selectedTenant,
    isAuthenticated: !!user,
    isLoadingAuth,
    selectTenant,
    login,
    register,
    logout,
    createTenant,
    refreshProfile: loadUserProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
