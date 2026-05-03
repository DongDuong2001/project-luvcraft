import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import { MapPin, Globe as Globe2, ChartBar as BarChart2, Hash, Stack as Layers } from '@phosphor-icons/react';

const mockRegionData = [
  { region: 'North America', volume: 450, sentiment: 82, color: '#3b82f6' },
  { region: 'Europe', volume: 320, sentiment: 75, color: '#10b981' },
  { region: 'Asia Pacific', volume: 550, sentiment: 88, color: '#8b5cf6' },
  { region: 'Latin America', volume: 180, sentiment: 64, color: '#f59e0b' },
  { region: 'MENA', volume: 220, sentiment: 71, color: '#ec4899' },
];

export default function GeoComparison() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <Globe2 className="h-7 w-7 text-emerald-500" /> Geo-Based Comparison
          </h2>
          <p className="text-sm text-slate-400 mt-1">Spatial analytics showing global reception, volume, and IP sentiment.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        
        {/* World Map Placeholder / Heatmap */}
        <Card className="col-span-1 xl:col-span-2 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white">Global IP Heatmap</CardTitle>
            <CardDescription className="text-slate-400">Interactive geographic visualization of community spread.</CardDescription>
          </CardHeader>
          <CardContent className="h-[450px] relative overflow-hidden rounded-md border border-app-line bg-app-bg m-6 mt-0 flex items-center justify-center">
            {/* Map Mock Graphic */}
            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiPjxwYXRoIGQ9Ik01MCwyNVExMDAsMTAwIDI1MCw1MFE0MDAsMTAwIDUwMCwyNSIgZmlsbD0idHJhbnNwYXJlbnQiIHN0cm9rZT0icmdiYSgyNTUsMjU1LDI1NSwwLjA1KSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtZGFzaGFycmF5PSI1LDUiLz48L3N2Zz4=')] opacity-30"></div>
            <Globe2 className="h-48 w-48 text-emerald-900/40 absolute -right-12 -bottom-12 animate-pulse" />
            
            <div className="z-10 text-center space-y-4">
               <div className="h-16 w-16 bg-emerald-500/10 border-2 border-emerald-500/50 rounded-full flex items-center justify-center mx-auto shadow-[0_0_30px_rgba(16,185,129,0.3)]">
                  <MapPin className="text-emerald-400 h-6 w-6" />
               </div>
               <p className="text-slate-500 text-sm italic">Interactive Leaflet / D3 Map Container</p>
               <div className="grid grid-cols-3 gap-2 text-xs">
                 <span className="bg-app-surface-strong text-slate-300 px-2 py-1 rounded">Zoom: 1x</span>
                 <span className="bg-app-surface-strong text-slate-300 px-2 py-1 rounded">Layer: Sentiment</span>
                 <span className="bg-app-surface-strong text-slate-300 px-2 py-1 rounded">Filter: Verified</span>
               </div>
            </div>
            
            {/* Floating Indicators */}
            <div className="absolute top-1/4 left-1/4 h-3 w-3 bg-blue-500 rounded-full shadow-[0_0_10px_rgba(59,130,246,0.8)] animate-bounce" />
            <div className="absolute top-[40%] right-[30%] h-4 w-4 bg-emerald-500 rounded-full shadow-[0_0_15px_rgba(16,185,129,0.8)] animate-pulse" />
            <div className="absolute bottom-[30%] left-[20%] h-2 w-2 bg-amber-500 rounded-full shadow-[0_0_8px_rgba(245,158,11,0.8)]" />
          </CardContent>
        </Card>

        {/* Region Breakdown List */}
        <Card className="col-span-1 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white flex items-center gap-2">
              <BarChart2 className="h-5 w-5 text-emerald-500" />
              Regional Breakdown
            </CardTitle>
            <CardDescription className="text-slate-400">Volume distribution metrics.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {mockRegionData.map((data, idx) => (
              <div key={idx} className="space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="font-semibold text-slate-200">{data.region}</span>
                  <span className="text-slate-400 font-mono">{data.volume}k hits</span>
                </div>
                {/* Progress Bar Mock */}
                <div className="w-full bg-app-surface-strong h-2.5 rounded-full overflow-hidden">
                  <div 
                    className="h-full rounded-full transition-all duration-1000 ease-out" 
                    style={{ width: `${(data.volume / 600) * 100}%`, backgroundColor: data.color }}
                  />
                </div>
                <div className="flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider pt-1">
                  <span>Sentiment:</span>
                  <span style={{ color: data.color }}>{data.sentiment}%</span>
                </div>
              </div>
            ))}

            <div className="pt-4 border-t border-app-line mt-4">
              <button className="w-full bg-app-surface-strong hover:bg-app-surface-strong border border-app-line text-slate-300 py-3 rounded-lg text-sm font-medium transition-colors">
                View Full Territory Matrix
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
