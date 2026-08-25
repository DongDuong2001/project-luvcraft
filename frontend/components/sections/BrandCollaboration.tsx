import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Users, Link, Medal as Award, PlayCircle, Heartbeat as HeartPulse, TreeStructure as Workflow, ArrowsLeftRight as ArrowRightLeft } from '@phosphor-icons/react';
import type { CollaborationCandidate } from '../../services/dashboard/dashboardService';

interface BrandCollaborationProps {
  keyword?: string;
  collaborations?: CollaborationCandidate[];
}

export default function BrandCollaboration({
  keyword,
  collaborations = [],
}: BrandCollaborationProps) {
  const displayCollaborations = collaborations.map((collab, index) => ({
    id: index + 1,
    name: collab.name,
    match: collab.collaborationScore,
    audiences: collab.audienceGrowth,
    type: collab.category,
    recommendation: collab.recommendation,
    isHeuristic: collab.isHeuristic ?? true,
    status: collab.status,
    audienceOverlap: collab.audienceOverlap,
    valueAlignment: collab.valueAlignment,
    riskSignals: collab.riskSignals,
    strengths: collab.strengths,
    weaknesses: collab.weaknesses,
    color: collab.collaborationScore >= 80 ? 'bg-emerald-500' : 'bg-blue-500',
  }));

  const primaryTarget = keyword && keyword.trim() ? keyword.trim() : null;
  const hasAnalysisData = primaryTarget && displayCollaborations.length > 0;
  const topPartner = displayCollaborations[0]?.name || 'No Brand Match';
  const topScore = displayCollaborations[0]?.match || 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">
            Brand-IP Collaboration Match {primaryTarget ? `— ${primaryTarget}` : ''}
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Keyword affinity profiles estimated from community signal topics and extracted keywords.
          </p>
        </div>
      </div>

      {!hasAnalysisData ? (
        <Card className="bg-app-surface border-app-line p-12 text-center text-slate-400">
          <Workflow className="h-12 w-12 text-slate-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">No Collaboration Data Available</h3>
          <p className="text-sm max-w-md mx-auto text-slate-400">
            {primaryTarget
              ? `No significant keyword crossover profiles found for "${primaryTarget}". Run an analysis with signals containing community keywords.`
              : 'Run an analysis on an IP or fandom keyword to generate keyword affinity profiles.'}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="col-span-1 lg:col-span-2 bg-app-surface border-app-line">
            <CardHeader>
              <CardTitle className="text-lg text-white">Network Affinity Graph ({primaryTarget})</CardTitle>
              <CardDescription className="text-slate-400">
                Visual mapping of audience topic intersection derived from extracted backend keywords.
              </CardDescription>
            </CardHeader>
            <CardContent className="h-[400px] flex items-center justify-center border border-dashed border-app-line rounded-lg bg-app-bg m-6 mt-0 relative overflow-hidden">
              <div className="absolute top-1/2 left-1/4 transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                <div className="h-16 w-16 bg-blue-600/20 border-2 border-blue-500 flex items-center justify-center rounded-full shadow-[0_0_15px_rgba(59,130,246,0.3)]">
                  <PlayCircle className="text-blue-400 h-6 w-6" />
                </div>
                <p className="text-xs text-white font-medium mt-2 max-w-[100px] truncate text-center">{primaryTarget}</p>
              </div>

              <div className="absolute top-1/2 left-3/4 transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center">
                <div className="h-14 w-14 bg-emerald-600/20 border-2 border-emerald-500 flex items-center justify-center rounded-full shadow-[0_0_15px_rgba(16,185,129,0.3)]">
                  <Workflow className="text-emerald-400 h-6 w-6" />
                </div>
                <p className="text-xs text-white font-medium mt-2 max-w-[100px] truncate text-center">{topPartner}</p>
              </div>

              <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-48 border-t-2 border-dashed border-blue-400/50 flex justify-center">
                <div className="bg-app-surface px-2 py-1 -mt-3 text-[10px] font-bold text-white border border-app-line rounded-md flex items-center gap-1">
                  <Link className="h-3 w-3 text-blue-400" /> +{topScore} Affinity
                </div>
              </div>

              <p className="absolute bottom-4 left-4 text-xs text-slate-500 flex items-center gap-1">
                <ArrowRightLeft className="h-3 w-3" /> Keyword Affinity Proxy Graph
              </p>
            </CardContent>
          </Card>

          <Card className="col-span-1 bg-app-surface border-app-line">
            <CardHeader>
              <CardTitle className="text-lg text-white flex items-center gap-2">
                <Award className="h-5 w-5 text-yellow-500" />
                Keyword Affinity Profiles
              </CardTitle>
              <CardDescription className="text-slate-400">
                Estimated from extracted community keywords and frequency.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {displayCollaborations.map((collab) => (
                <article key={collab.id} className="rounded-xl border border-app-line bg-app-surface-strong p-4">
                  <div className="flex justify-between items-start mb-1">
                    <h3 className="text-sm font-semibold text-white">{collab.name}</h3>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${collab.color}/20 border border-blue-500/30`} aria-label={`Collaboration score ${collab.match} out of 100`}>
                      {collab.status === 'analyzed' ? `${collab.match} Score` : 'Insufficient data'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-2 italic">{collab.recommendation}</p>
                  <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-app-line/50">
                    <div className="flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {collab.audiences}</div>
                    <div className="flex items-center gap-1"><HeartPulse className="h-3.5 w-3.5" /> {collab.type}</div>
                  </div>
                  {collab.status === 'analyzed' && <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400">
                    <span>Audience overlap: {collab.audienceOverlap === null ? '—' : `${Math.round(collab.audienceOverlap * 100)}%`}</span>
                    <span>Value alignment: {collab.valueAlignment === null ? '—' : `${Math.round(collab.valueAlignment * 100)}%`}</span>
                  </div>}
                  {collab.strengths.length > 0 && <p className="mt-2 text-xs text-emerald-300">Strengths: {collab.strengths.join(' · ')}</p>}
                  {collab.riskSignals.length > 0 && <p className="mt-2 text-xs text-amber-300">Risks: {collab.riskSignals.join(' · ')}</p>}
                </article>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
