import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Search, Filter, ChevronLeft, ChevronRight, Download, MoreHorizontal } from 'lucide-react';

const mockHistory = [
  { id: '1', keyword: 'Cyberpunk 2077', date: '2026-04-28', status: 'Completed', sentiment: 78, volume: '2.1M' },
  { id: '2', keyword: 'Dune: Awakening', date: '2026-04-25', status: 'Completed', sentiment: 85, volume: '840K' },
  { id: '3', keyword: 'Attack on Titan', date: '2026-04-20', status: 'Completed', sentiment: 92, volume: '3.4M' },
  { id: '4', keyword: 'Star Wars: Eclipse', date: '2026-04-18', status: 'Processing', sentiment: '--', volume: '--' },
  { id: '5', keyword: 'Warhammer 40k', date: '2026-04-12', status: 'Completed', sentiment: 64, volume: '1.2M' },
  { id: '6', keyword: 'Fallout Amazon', date: '2026-04-05', status: 'Completed', sentiment: 88, volume: '4.1M' },
];

export default function HistoricalResearch() {
  const [searchTerm, setSearchTerm] = useState('');

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
                {mockHistory.map((row) => (
                  <tr key={row.id} className="hover:bg-app-surface-strong transition-colors text-slate-300">
                    <td className="px-6 py-4 font-medium text-white">{row.keyword}</td>
                    <td className="px-6 py-4">{row.date}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 flex items-center w-max rounded-full text-[10px] font-bold tracking-wider uppercase ${
                        row.status === 'Completed' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                        {row.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">{row.sentiment}</td>
                    <td className="px-6 py-4">{row.volume}</td>
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
            <p className="text-xs text-slate-500">Showing <span className="text-white">1</span> to <span className="text-white">6</span> of <span className="text-white">24</span> results</p>
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
