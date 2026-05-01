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
            <CardDescription className="text-slate-400">Configure identity providers for enterprise access.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
             <div className="p-4 rounded-lg bg-[#050505] border border-[#1f1f22] space-y-4">
                <div className="flex items-center justify-between border-b border-[#1f1f22] pb-4">
                   <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded bg-blue-600 flex items-center justify-center font-bold text-white shadow-lg">G</div>
                      <div>
                        <h4 className="text-sm font-semibold text-slate-200">Google Workspace</h4>
                        <p className="text-xs text-slate-500">Configured and Active</p>
                      </div>
                   </div>
                   <Button variant="outline" size="sm" className="h-8 text-xs border-[#3f3f46] text-slate-300">Disable</Button>
                </div>
                
                <div className="flex items-center justify-between border-b border-[#1f1f22] pb-4">
                   <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded bg-[#0078D4] flex items-center justify-center font-bold text-white shadow-lg">
                        M
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-slate-200">Microsoft Entra ID</h4>
                        <p className="text-xs text-slate-500">Service Principal Required</p>
                      </div>
                   </div>
                   <Button size="sm" className="h-8 text-xs bg-purple-600 hover:bg-purple-700 text-white">Configure</Button>
                </div>

                <div className="flex items-center justify-between">
                   <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded bg-[#1f1f22] border border-[#3f3f46] flex items-center justify-center font-bold text-slate-400 shadow-lg">
                         <KeyRound className="h-4 w-4" />
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-slate-200">Custom SAML 2.0</h4>
                        <p className="text-xs text-slate-500">Setup SP/IdP Metadata</p>
                      </div>
                   </div>
                   <Button size="sm" variant="ghost" className="h-8 text-xs text-slate-400 hover:text-white">Learn More</Button>
                </div>
             </div>

             {/* API Keys */}
             <div className="mt-8 space-y-3">
                <h4 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                  <RefreshCcw className="h-4 w-4 text-emerald-500" /> Platform API Keys
                </h4>
                <div className="flex items-center gap-2 p-1.5 bg-[#141418] rounded-md border border-[#1f1f22]">
                   <Input 
                      type="password" 
                      value="luvc_live_********************************" 
                      readOnly 
                      className="bg-transparent border-none text-slate-300 h-8 font-mono text-xs focus-visible:ring-0" 
                   />
                   <Button size="sm" variant="ghost" className="h-8 px-3 text-slate-400 hover:text-white">Copy</Button>
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