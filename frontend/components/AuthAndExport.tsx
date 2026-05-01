import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { KeyRound, Download, Fingerprint, RefreshCcw, LayoutDashboard, Send } from 'lucide-react';

export default function AuthAndExport() {
  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between pt-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
             Authentication & Report Export
          </h2>
          <p className="text-sm text-slate-400 mt-1">SSO Configuration and Insight Exportation Engine.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mt-8">
        
        {/* Authentication & SSO */}
        <Card className="bg-[#0c0c0e] border-[#1f1f22]">
          <CardHeader>
            <CardTitle className="text-lg text-white flex items-center gap-2">
              <Fingerprint className="h-5 w-5 text-purple-500" /> Authentication & SSO
            </CardTitle>
            <CardDescription className="text-slate-400">Configure SSO Login integration for your workspace.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
             <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Enterprise Email Domain</label>
                  <Input 
                      type="email" 
                      placeholder="e.g. company.com" 
                      className="bg-[#050505] border-[#1f1f22] text-slate-300 focus-visible:ring-0" 
                   />
                </div>
                <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white">
                  Enable SSO Routing
                </Button>
                
                <div className="relative py-2">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-[#1f1f22]" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-[#0c0c0e] px-2 text-slate-500">Supported Providers</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                   <div className="flex items-center justify-center gap-2 p-3 rounded-md border border-[#1f1f22] bg-[#050505]">
                      <div className="h-6 w-6 rounded bg-blue-600 flex items-center justify-center font-bold text-white text-xs">G</div>
                      <span className="text-sm text-slate-300">Google</span>
                   </div>
                   <div className="flex items-center justify-center gap-2 p-3 rounded-md border border-[#1f1f22] bg-[#050505]">
                      <div className="h-6 w-6 rounded bg-[#0078D4] flex items-center justify-center font-bold text-white text-xs">M</div>
                      <span className="text-sm text-slate-300">Microsoft</span>
                   </div>
                </div>

                <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/20 rounded-md">
                   <p className="text-xs text-purple-300 text-center">
                     * Password inputs are disabled in this dashboard. All user authentication is fully delegated to your secure Identity Provider (IdP).
                   </p>
                </div>
             </div>
          </CardContent>
        </Card>

        {/* Report Export Module */}
        <Card className="bg-[#0c0c0e] border-[#1f1f22]">
          <CardHeader>
            <CardTitle className="text-lg text-white flex items-center gap-2">
              <Download className="h-5 w-5 text-blue-500" /> Report Export Module
            </CardTitle>
            <CardDescription className="text-slate-400">Generate and distribute analytics reports.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="p-4 rounded-lg bg-[#050505] border border-[#1f1f22] text-center space-y-3 hover:border-blue-500/50 cursor-pointer transition-colors group">
                 <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/20 group-hover:bg-blue-500/20">
                   <LayoutDashboard className="h-6 w-6 text-blue-400" />
                 </div>
                 <div>
                   <h4 className="text-sm font-semibold text-slate-200">Slide Deck (.pptx)</h4>
                   <p className="text-xs text-slate-500">Exec Summary</p>
                 </div>
              </div>
              <div className="p-4 rounded-lg bg-[#050505] border border-[#1f1f22] text-center space-y-3 hover:border-emerald-500/50 cursor-pointer transition-colors group">
                 <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20 group-hover:bg-emerald-500/20">
                   <Send className="h-6 w-6 text-emerald-400" />
                 </div>
                 <div>
                   <h4 className="text-sm font-semibold text-slate-200">Data Dump (.csv)</h4>
                   <p className="text-xs text-slate-500">Raw Analytics</p>
                 </div>
              </div>
            </div>

            <div className="space-y-3 pt-6 border-t border-[#1f1f22]">
               <h4 className="text-sm font-semibold text-slate-300">Automated Distribution</h4>
               <div className="flex gap-3">
                 <Input placeholder="marketing@company.com, exec@company.com" className="bg-[#050505] border-[#1f1f22] text-slate-300 h-10" />
                 <Button className="bg-blue-600 hover:bg-blue-700 text-white h-10 whitespace-nowrap">
                    Schedule Export
                 </Button>
               </div>
            </div>

          </CardContent>
        </Card>
      </div>
    </div>
  );
}