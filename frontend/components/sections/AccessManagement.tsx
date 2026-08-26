import { useCallback, useEffect, useState } from 'react';
import { Shield, ClockCounterClockwise as History, Pulse as Activity } from '@phosphor-icons/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { apiClient, getApiErrorMessage } from '../../services/core/apiClient';
import type { UserRole } from '../../state/auth/AuthContext';

interface ManagedUser {
  user_id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  brand_id: string | null;
  is_active: boolean;
  created_at: string;
}

interface AuditEntry {
  log_id: string;
  actor_email: string;
  action_type: string;
  created_at: string;
}

interface BrandOption {
  brand_id: string;
  brand_name: string;
}

const ROLES: UserRole[] = ['admin', 'analyst', 'client', 'viewer'];

export default function AccessManagement() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [brands, setBrands] = useState<BrandOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatingUserIds, setUpdatingUserIds] = useState<Set<string>>(new Set());
  const [success, setSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null); setSuccess(null);
    try {
      const [nextUsers, nextLogs, nextBrands] = await Promise.all([
        apiClient.get<ManagedUser[]>('/admin/users'),
        apiClient.get<AuditEntry[]>('/admin/audit-logs?limit=20'),
        apiClient.get<BrandOption[]>('/brands'),
      ]);
      setUsers(nextUsers);
      setAuditLogs(nextLogs);
      setBrands(nextBrands);
    } catch (caught) {
      setError(getApiErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData]);

  const updateUser = async (
    userId: string,
    update: { role?: UserRole; is_active?: boolean; brand_id?: string | null; update_brand?: boolean },
  ) => {
    setError(null); setSuccess(null);
    setUpdatingUserIds((prev) => new Set(prev).add(userId));
    try {
      const updated = await apiClient.patch<ManagedUser>(`/admin/users/${userId}`, update);
      setUsers((current) => current.map((user) => user.user_id === userId ? updated : user));
      setAuditLogs(await apiClient.get<AuditEntry[]>('/admin/audit-logs?limit=20'));
      setSuccess(`Access settings for ${updated.email} were saved.`);
    } catch (caught) {
      setError(getApiErrorMessage(caught));
    } finally {
      setUpdatingUserIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between pt-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <Shield className="h-7 w-7 text-blue-400" /> Access & Security
          </h2>
          <p className="text-sm text-slate-400 mt-1">Manage server-authoritative roles and account status.</p>
        </div>
        <Button onClick={() => void loadData()} disabled={loading} variant="outline" className="bg-app-surface border-app-line text-slate-300">{loading ? 'Refreshing…' : 'Refresh'}</Button>
      </div>

      {error && <div role="alert" className="flex items-center justify-between gap-3 border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300"><span>{error}</span><Button size="sm" variant="outline" onClick={() => void loadData()}>Retry</Button></div>}
      {success && <div role="status" aria-live="polite" className="flex items-center justify-between gap-3 border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300"><span>{success}</span><Button size="sm" variant="ghost" className="h-7 text-xs text-emerald-300 hover:text-emerald-100" onClick={() => setSuccess(null)}>Dismiss</Button></div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
        <Card className="lg:col-span-2 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white">Users</CardTitle>
            <CardDescription className="text-slate-400">Changes are audited and applied immediately.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? <p className="text-sm text-slate-400">Loading access profiles…</p> : (
              <div className="space-y-3">
                {users.map((user) => (
                  <div key={user.user_id} className="flex flex-col gap-3 rounded-lg border border-app-line bg-app-bg p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h4 className="text-sm font-semibold text-slate-200">{user.full_name || user.email}</h4>
                      <p className="text-xs text-slate-500">{user.email}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <select
                        aria-label={`Role for ${user.email}`}
                        value={user.role}
                        disabled={updatingUserIds.has(user.user_id)}
                        onChange={(event) => void updateUser(user.user_id, { role: event.target.value as UserRole })}
                        className="h-9 rounded-md border border-app-line bg-app-surface-strong px-2 text-xs text-slate-200"
                      >
                        {ROLES.map((role) => <option key={role} value={role}>{role}</option>)}
                      </select>
                      <select
                        aria-label={`Brand for ${user.email}`}
                        value={user.brand_id || ''}
                        disabled={updatingUserIds.has(user.user_id)}
                        onChange={(event) => void updateUser(user.user_id, {
                          brand_id: event.target.value || null,
                          update_brand: true,
                        })}
                        className="h-9 max-w-40 rounded-md border border-app-line bg-app-surface-strong px-2 text-xs text-slate-200"
                      >
                        <option value="">No brand</option>
                        {brands.map((brand) => <option key={brand.brand_id} value={brand.brand_id}>{brand.brand_name}</option>)}
                      </select>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void updateUser(user.user_id, { is_active: !user.is_active })}
                        disabled={updatingUserIds.has(user.user_id)}
                        className={user.is_active ? 'border-emerald-500/30 text-emerald-400' : 'border-slate-600 text-slate-400'}
                      >
                        <Activity className="mr-1 h-3 w-3" /> {user.is_active ? 'Active' : 'Inactive'}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-sm text-white flex items-center gap-2"><History className="h-4 w-4 text-blue-400" /> Recent Audit Events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {auditLogs.length === 0 && <p className="text-xs text-slate-500">No audited changes yet.</p>}
            {auditLogs.map((entry) => (
              <div key={entry.log_id} className="border-b border-app-line pb-3 last:border-0">
                <p className="text-xs font-medium text-slate-300">{entry.action_type}</p>
                <p className="mt-1 text-[11px] text-slate-500">{entry.actor_email} · {new Date(entry.created_at).toLocaleString()}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
