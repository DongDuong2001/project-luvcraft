import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Shield, Key, Users, ClockCounterClockwise as History, Pulse as Activity, Lock, WarningCircle as AlertCircle } from '@phosphor-icons/react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';

export default function AccessManagement() {
  const users = [
    { name: 'Sarah Chen', role: 'Admin', email: 'sarah@luvcraft.io', status: 'Active', activity: '2 mins ago' },
    { name: 'Marcus Doe', role: 'Analyst', email: 'marcus@luvcraft.io', status: 'Active', activity: '1 hour ago' },
    { name: 'Elena Rostova', role: 'Viewer', email: 'elena@external.com', status: 'Inactive', activity: '3 days ago' },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between pt-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <Shield className="h-7 w-7 text-blue-400" /> Access & Security
          </h2>
          <p className="text-sm text-slate-400 mt-1">Manage user roles, permissions, and security policies.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="bg-app-surface border-app-line text-slate-300">
            <History className="h-4 w-4 mr-2" /> Audit Log
          </Button>
          <Button className="bg-app-accent hover:bg-app-accent-hover text-white">
            <Users className="h-4 w-4 mr-2" /> Invite User
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
        {/* User List */}
        <Card className="col-span-2 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white">Team Members</CardTitle>
            <CardDescription className="text-slate-400">Active personnel and API keys.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {users.map((user, idx) => (
                <div key={idx} className="flex items-center justify-between p-4 rounded-lg bg-app-bg border border-app-line">
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-full bg-blue-500/20 text-blue-300 flex items-center justify-center font-bold">
                      {user.name.charAt(0)}
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-slate-200">{user.name}</h4>
                      <p className="text-xs text-slate-500">{user.email}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="text-xs font-mono px-2 py-1 rounded bg-app-surface-strong text-slate-300 border border-app-line">
                      {user.role}
                    </span>
                    <span className={`text-[10px] uppercase font-bold flex items-center gap-1 ${user.status === 'Active' ? 'text-emerald-500' : 'text-slate-500'}`}>
                      <Activity className="h-3 w-3" /> {user.activity}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Security Policies */}
        <div className="space-y-6">
          <Card className="bg-app-surface border-app-line">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                <Lock className="h-4 w-4 text-rose-500" /> Security Policies
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-400">
              <div className="flex items-center justify-between">
                <span>Multi-Factor Auth</span>
                <span className="px-2 py-0.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Required</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Session Timeout</span>
                <span className="text-slate-200">12 Hours</span>
              </div>
              <div className="flex items-center justify-between">
                <span>API Key Expiry</span>
                <span className="text-slate-200">30 Days</span>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-rose-500/5 border-rose-500/20">
            <CardContent className="p-4 flex gap-3">
              <AlertCircle className="h-5 w-5 text-rose-400 flex-shrink-0" />
              <div className="space-y-1">
                <h4 className="text-sm font-medium text-rose-200">Critical Alert</h4>
                <p className="text-xs text-rose-400/80">3 failed login attempts from unknown IP address. Review audit logs immediately.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
