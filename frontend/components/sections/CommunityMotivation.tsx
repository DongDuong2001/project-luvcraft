import { ChatCircleText, Heart, Megaphone, Users } from '@phosphor-icons/react';
import type { CommunityMotivation as CommunityMotivationData, MotivationFinding } from '../../services/dashboard/dashboardService';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';

const title = (value: string | null) => value ? value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()) : 'Unavailable';

function FindingList({ heading, findings }: { heading: string; findings: MotivationFinding[] }) {
  return <div><h4 className="text-sm font-semibold text-slate-200">{heading}</h4>{findings.length ? <ul className="mt-2 space-y-2">{findings.map((finding) => <li key={`${heading}-${finding.topic}`} className="rounded-lg border border-app-line bg-app-surface-strong p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-white">{finding.topic}</span><span className="text-xs text-blue-300">{finding.mentionCount} mention{finding.mentionCount === 1 ? '' : 's'}</span></div><p className="mt-1 text-xs leading-relaxed text-slate-400">{finding.reason}</p><p className="mt-2 text-xs text-slate-500">Sentiment: {finding.sentimentScore === null ? 'Unavailable' : `${finding.sentimentScore.toFixed(1)}/100`} · Evidence: {finding.evidenceSignalIds.length} stored signal{finding.evidenceSignalIds.length === 1 ? '' : 's'}</p></li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No supported findings.</p>}</div>;
}

export default function CommunityMotivation({ data }: { data: CommunityMotivationData }) {
  const { community, motivations } = data;
  return <section aria-labelledby="community-motivation-heading" className="space-y-6">
    <div><h2 id="community-motivation-heading" className="text-xl font-bold text-white">Community & Motivation</h2><p className="mt-1 text-sm text-slate-400">Structured findings derived from stored text and engagement evidence.</p></div>
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card className="border-app-line bg-app-surface text-white"><CardHeader><CardTitle className="flex items-center gap-2"><Users aria-hidden="true" className="h-5 w-5 text-blue-400" />Community and Fandom</CardTitle><CardDescription className="text-slate-400">Audience, interaction quality, safety and consensus.</CardDescription></CardHeader><CardContent>
        {community.status === 'analyzed' ? <><dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">{[['Engagement', community.engagementLevel], ['Discussion depth', community.discussionDepth], ['Toxicity', community.toxicityLevel], ['Hospitality', community.hospitalityLevel], ['Consensus', community.consensusLevel]].map(([label, value]) => <div key={label} className="rounded-lg border border-app-line p-3"><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-semibold">{title(value)}</dd></div>)}</dl><h4 className="mt-5 text-sm font-semibold">Audience segments</h4><ul className="mt-2 space-y-2">{community.audienceSegments.map((segment) => <li key={segment.segment} className="flex flex-wrap justify-between gap-2 rounded-lg bg-app-surface-strong p-3 text-sm"><span>{title(segment.segment)}</span><span className="text-slate-400">{segment.signalCount} signals · {Math.round(segment.share * 100)}% share · {segment.evidenceSignalIds.length} evidence</span></li>)}</ul>{community.warnings.map((warning) => <p key={warning} className="mt-3 text-xs text-amber-300">{warning}</p>)}</> : <p role="status" className="text-sm text-slate-400">Insufficient text evidence for community analysis.</p>}
      </CardContent></Card>
      <Card className="border-app-line bg-app-surface text-white"><CardHeader><CardTitle className="flex items-center gap-2"><Heart aria-hidden="true" className="h-5 w-5 text-rose-400" />Engagement Motivation</CardTitle><CardDescription className="text-slate-400">What people explicitly like, dislike, praise, request or complain about.</CardDescription></CardHeader><CardContent>
        {motivations.status === 'analyzed' ? <div className="grid grid-cols-1 gap-5 sm:grid-cols-2"><FindingList heading="Likes" findings={motivations.likes} /><FindingList heading="Praise" findings={motivations.praise} /><FindingList heading="Dislikes" findings={motivations.dislikes} /><FindingList heading="Complaints" findings={motivations.complaints} /><div className="sm:col-span-2"><FindingList heading="Unmet expectations" findings={motivations.unmetExpectations} /></div></div> : <p role="status" className="flex items-center gap-2 text-sm text-slate-400"><ChatCircleText aria-hidden="true" />No explicit motivation evidence was found; no generic claims were generated.</p>}
      </CardContent></Card>
    </div>
    <p className="sr-only"><Megaphone aria-hidden="true" />Evidence counts refer to stored signal identifiers.</p>
  </section>;
}
