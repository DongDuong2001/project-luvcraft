import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';
import { Database, Filter, Gauge, Layers, Target, Activity } from 'lucide-react';
import { Button } from './ui/button';

const mockRadarData = [
  { subject: 'Engagement', A: 120, B: 110, fullMark: 150 },
  { subject: 'Sentiment', A: 98, B: 130, fullMark: 150 },
  { subject: 'Virality', A: 86, B: 130, fullMark: 150 },
  { subject: 'Brand Fit', A: 99, B: 100, fullMark: 150 },
  { subject: 'Demographic', A: 85, B: 90, fullMark: 150 },
  { subject: 'Growth Rate', A: 65, B: 85, fullMark: 150 },
];

export default function MultiDimensionalInsights() {
  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between pt-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-3">
            <Layers className="h-7 w-7 text-blue-400" /> Multi-Dimensional Insights
          </h2>
          <p className="text-sm text-slate-400 mt-1">Cross-reference diverse data planes to uncover hidden correlations.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" className="bg-app-surface border-app-line text-slate-300">
            <Filter className="h-4 w-4 mr-2" /> Add Dimension
          </Button>
          <Button className="bg-app-accent hover:bg-app-accent-hover text-white">
            <Activity className="h-4 w-4 mr-2" /> Run Analysis
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
        {/* Radar Chart Analysis */}
        <Card className="col-span-2 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white flex items-center gap-2">
              <Target className="h-5 w-5 text-blue-300" /> Vector Analysis
            </CardTitle>
            <CardDescription className="text-slate-400">Comparing current IP against industry benchmarks.</CardDescription>
          </CardHeader>
          <CardContent className="h-[400px] mt-4 flex items-center justify-center pt-8 pr-12 pb-8 pl-4">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart cx="50%" cy="50%" outerRadius="80%" data={mockRadarData}>
                <PolarGrid stroke="#3f3f46" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <PolarRadiusAxis angle={30} domain={[0, 150]} tick={false} axisLine={false} />
                <Radar name="Target IP" dataKey="A" stroke="#2573ff" fill="#2573ff" fillOpacity={0.28} />
                <Radar name="Benchmark" dataKey="B" stroke="#92b9ff" fill="#92b9ff" fillOpacity={0.22} />
                <RechartsTooltip 
                  contentStyle={{ backgroundColor: '#000000', borderColor: '#2b3447', color: '#f8fafc', borderRadius: '8px' }}
                  itemStyle={{ color: '#92b9ff' }} 
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
          <div className="flex justify-center gap-6 pb-6 pt-2">
             <div className="flex items-center gap-2 text-sm text-slate-400"><div className="h-3 w-3 bg-[#2573ff] rounded-full" /> Target IP</div>
             <div className="flex items-center gap-2 text-sm text-slate-400"><div className="h-3 w-3 bg-[#92b9ff] rounded-full" /> Benchmark</div>
          </div>
        </Card>

        {/* Insight Panels */}
        <div className="space-y-6">
          <Card className="bg-app-surface border-app-line">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                <Database className="h-4 w-4 text-emerald-500" /> Statistical Significance
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-400 pt-2">
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center text-slate-200">
                   <span className="font-semibold">Correlation Coeff.</span>
                   <span className="font-mono text-emerald-400">+0.84</span>
                </div>
                <div className="flex justify-between items-center text-slate-200 border-t border-app-line pt-3">
                   <span className="font-semibold">P-Value</span>
                   <span className="font-mono text-blue-400">&lt; 0.05</span>
                </div>
                <div className="flex justify-between items-center text-slate-200 border-t border-app-line pt-3">
                   <span className="font-semibold">Confidence Interval</span>
                   <span className="font-mono text-blue-300">95%</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-blue-500/5 border-blue-500/20">
            <CardContent className="p-4 flex gap-3">
              <Gauge className="h-5 w-5 text-blue-300 flex-shrink-0" />
              <div className="space-y-1">
                <h4 className="text-sm font-medium text-blue-200">Velocity Indicator</h4>
                <p className="text-xs text-blue-300/80">The target IP is showing unprecedented growth in Gen-Z demographics compared to the benchmark.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
