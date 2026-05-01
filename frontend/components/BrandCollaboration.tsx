import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Users, Link, Award, PlayCircle, HeartPulse, Workflow, ArrowRightLeft } from 'lucide-react';

const mockCollaborations = [
  { id: 1, name: 'Fortnite x Cyberpunk', match: 94, audiences: 'Overlap: 65%', type: 'Games Crossover', color: 'bg-emerald-500' },
  { id: 2, name: 'Nike x Arcane', match: 88, audiences: 'Overlap: 40%', type: 'Apparel', color: 'bg-blue-500' },
  { id: 3, name: 'RedBull x Valorant', match: 91, audiences: 'Overlap: 80%', type: 'F&B Esports', color: 'bg-blue-500' },
  { id: 4, name: 'Gucci x Final Fantasy', match: 72, audiences: 'Overlap: 25%', type: 'Luxury Fashion', color: 'bg-amber-500' },
];

export default function BrandCollaboration() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Brand-IP Collaboration Match</h2>
          <p className="text-sm text-slate-400 mt-1">Discover high-affinity IP crossovers backed by audience overlap data.</p>
        </div>
        <Button className="bg-app-accent hover:bg-app-accent-hover text-white">
          <Workflow className="mr-2 h-4 w-4" /> Run Match Analysis
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="col-span-1 lg:col-span-2 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white">Network Affinity Graph</CardTitle>
            <CardDescription className="text-slate-400">Visual mapping of audience intersection between requested IP and brands.</CardDescription>
          </CardHeader>
          <CardContent className="h-[400px] flex items-center justify-center border border-dashed border-app-line rounded-lg bg-app-bg m-6 mt-0 relative overflow-hidden">
            {/* Mock Network Diagram Structure */}
            <div className="absolute top-1/2 left-1/4 transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
              <div className="h-16 w-16 bg-blue-600/20 border-2 border-blue-500 flex items-center justify-center rounded-full shadow-[0_0_15px_rgba(59,130,246,0.3)]">
                <PlayCircle className="text-blue-400 h-6 w-6" />
              </div>
              <p className="text-xs text-white font-medium mt-2">Cyberpunk</p>
            </div>

            <div className="absolute top-1/2 left-3/4 transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
              <div className="h-14 w-14 bg-emerald-600/20 border-2 border-emerald-500 flex items-center justify-center rounded-full shadow-[0_0_15px_rgba(16,185,129,0.3)]">
                <Workflow className="text-emerald-400 h-6 w-6" />
              </div>
              <p className="text-xs text-white font-medium mt-2">Fortnite</p>
            </div>

            {/* Connection Line */}
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-48 border-t-2 border-dashed border-blue-400/50 flex justify-center">
              <div className="bg-app-surface px-2 py-1 -mt-3 text-[10px] font-bold text-white border border-app-line rounded-md flex items-center gap-1">
                <Link className="h-3 w-3 text-blue-400" /> +94 Match
              </div>
            </div>
            
            <p className="absolute bottom-4 left-4 text-xs text-slate-500 flex items-center gap-1">
              <ArrowRightLeft className="h-3 w-3" /> AI Node Force-Directed Graph Preview
            </p>
          </CardContent>
        </Card>

        <Card className="col-span-1 bg-app-surface border-app-line">
          <CardHeader>
            <CardTitle className="text-lg text-white flex items-center gap-2">
              <Award className="h-5 w-5 text-yellow-500" />
              Top Match Profiles
            </CardTitle>
            <CardDescription className="text-slate-400">Ranked by audience sentiment and category overlap.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {mockCollaborations.map((collab) => (
              <div key={collab.id} className="p-4 rounded-xl border border-app-line bg-app-surface-strong hover:bg-app-surface-strong transition-colors group cursor-pointer">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="text-sm font-semibold text-white">{collab.name}</h3>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${collab.color}/20 text-white border border-${collab.color.split('-')[1]}-500/30`}>
                    {collab.match}% Score
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-400 mt-3">
                  <div className="flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {collab.audiences}</div>
                  <div className="flex items-center gap-1"><HeartPulse className="h-3.5 w-3.5" /> {collab.type}</div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
