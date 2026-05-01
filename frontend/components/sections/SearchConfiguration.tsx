import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Code, Database, Search, Settings, SortAsc, Tags, Zap, Filter } from 'lucide-react';

export default function SearchConfiguration() {
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState('all');

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-col gap-4 pt-6">
        <div className="text-center space-y-4">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20">
            <Settings className="h-6 w-6 text-blue-300" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-white">Search & Command Center</h2>
          <p className="text-base text-slate-400">Advanced query configuration and real-time deep scans.</p>
        </div>
      </div>

      <Card className="bg-app-surface border-app-line overflow-hidden mt-8 shadow-2xl">
        <CardContent className="p-0">
          <div className="p-6 border-b border-app-line bg-app-bg">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-500 pointer-events-none" />
              <Input
                autoFocus
                placeholder="Type a command, query, or IP name (e.g. '> analyze Genshin Impact')..."
                className="h-16 pl-12 text-lg bg-app-surface border-2 border-app-line focus:border-blue-500/50 text-white rounded-xl shadow-inner placeholder:text-slate-600"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
                <kbd className="hidden sm:inline-flex px-2 py-1 items-center gap-1 rounded bg-app-surface-strong text-[10px] font-mono text-slate-400 font-semibold border border-app-line">
                  Ctrl K
                </kbd>
              </div>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-4 min-h-[300px] bg-app-bg">
            {/* Sidebar Filters */}
            <div className="col-span-1 border-r border-app-line bg-app-bg-soft p-4 flex flex-col gap-4">
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Platforms</h4>
                <div className="space-y-1">
                  {['all', 'reddit', 'twitter', 'youtube', 'tiktok'].map(p => (
                    <button 
                      key={p}
                      onClick={() => setPlatform(p)}
                      className={`w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                        platform === p ? 'bg-blue-500/10 text-blue-300 border border-blue-500/20' : 'text-slate-400 hover:bg-app-surface-strong hover:text-white'
                      }`}
                    >
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 mt-4">Modifiers</h4>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <input type="checkbox" className="rounded bg-app-surface-strong border-app-line text-blue-500 focus:ring-blue-500" defaultChecked />
                    Include Sentiment
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <input type="checkbox" className="rounded bg-app-surface-strong border-app-line text-blue-500 focus:ring-blue-500" defaultChecked />
                    Exclude Bot Spam
                  </label>
                </div>
              </div>
            </div>

            {/* Results / Suggestion Pane */}
            <div className="col-span-3 p-4 bg-app-bg">
              {query === '' ? (
                <>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                    <Zap className="h-3 w-3" /> Recent & Suggested
                  </h4>
                  <div className="grid gap-2">
                    {['Compare Marvel vs DC', 'Analyze Elden Ring demographic', 'Export Cyberpunk slide deck'].map(item => (
                      <div key={item} className="flex items-center px-3 py-3 text-sm text-slate-300 rounded-lg hover:bg-app-surface-strong hover:text-white cursor-pointer transition-colors border border-transparent hover:border-app-line">
                        <Search className="mr-3 h-4 w-4 text-slate-500" />
                        {item}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center space-y-3 opacity-60">
                  <Database className="h-8 w-8 text-slate-500 animate-pulse" />
                  <p className="text-sm text-slate-400">Searching global databases for <span className="text-white font-semibold">{query}</span>...</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

