import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { MagnifyingGlass as Search, Funnel as Filter, CaretLeft as ChevronLeft, CaretRight as ChevronRight, Download, DotsThree as MoreHorizontal } from '@phosphor-icons/react';

import { dashboardService } from '../../services/dashboard/dashboardService';

interface HistoricalRun {
  run_id: string;
  keyword: string;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export default function HistoricalResearch() {
  const [searchTerm, setSearchTerm] = useState('');
  const [history, setHistory] = useState<HistoricalRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  React.useEffect(() => {
    dashboardService.getHistoricalRuns()
      .then(data => setHistory(data))
      .catch(err => console.error("Failed to load historical runs", err))
      .finally(() => setIsLoading(false));
  }, []);

  const filteredHistory = history.filter(run => 
    run.keyword.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Historical Research</h2>
          <p className="text-sm text-slate-400 mt-1">Review past intelligence reports and sentiment snapshots.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="border-app-line bg-transparent text-slate-300 hover:bg-app-surface-strong">
            <Filter className="mr-2 h-4 w-4" /> Filter
          </Button>
          <Button className="bg-blue-600 hover:bg-blue-700 text-white">
            <Download className="mr-2 h-4 w-4" /> Export All
          </Button>
        </div>
      </div>

      <Card className="bg-app-surface border-app-line">
        <CardHeader className="border-b border-app-line pb-4">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
            <Input
              placeholder="Search reports..."
              className="pl-9 bg-app-bg border-app-line text-white"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-app-surface-strong text-slate-400 uppercase text-xs tracking-wider border-b border-app-line">
                <tr>
                  <th className="px-6 py-4 font-medium">IP / Keyword</th>
                  <th className="px-6 py-4 font-medium">Run Date</th>
                  <th className="px-6 py-4 font-medium">Status</th>
                  <th className="px-6 py-4 font-medium">Avg Sentiment</th>
                  <th className="px-6 py-4 font-medium">Volume</th>
                  <th className="px-6 py-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-app-line">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-slate-400">Loading historical data...</td>
                  </tr>
                ) : filteredHistory.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-8 text-center text-slate-400">No historical runs found.</td>
                  </tr>
                ) : filteredHistory.map((row) => (
                  <tr key={row.run_id} className="hover:bg-app-surface-strong transition-colors text-slate-300">
                    <td className="px-6 py-4 font-medium text-white">{row.keyword}</td>
                    <td className="px-6 py-4">{new Date(row.created_at).toLocaleDateString()}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 flex items-center w-max rounded-full text-[10px] font-bold tracking-wider uppercase ${
                        row.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                        : row.status === 'failed' ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                        : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                        {row.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">--</td>
                    <td className="px-6 py-4">--</td>
                    <td className="px-6 py-4 text-right">
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-white hover:bg-app-surface-strong">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          <div className="flex items-center justify-between px-6 py-4 border-t border-app-line">
            <p className="text-xs text-slate-500">Showing <span className="text-white">{filteredHistory.length > 0 ? 1 : 0}</span> to <span className="text-white">{filteredHistory.length}</span> of <span className="text-white">{filteredHistory.length}</span> results</p>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" className="border-app-line bg-transparent text-slate-400 disabled:opacity-50">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" className="border-app-line bg-app-surface-strong text-white">1</Button>
              <Button variant="outline" size="sm" className="border-app-line bg-transparent text-slate-400 hover:bg-app-surface-strong">2</Button>
              <Button variant="outline" size="sm" className="border-app-line bg-transparent text-slate-400 hover:bg-app-surface-strong">3</Button>
              <Button variant="outline" size="sm" className="border-app-line bg-transparent text-slate-400">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
