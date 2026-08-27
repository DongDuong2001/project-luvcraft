import { useEffect, useMemo, useState } from 'react';
import { ArrowsLeftRight, CheckCircle, FloppyDisk, Plus, SpinnerGap, Warning } from '@phosphor-icons/react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { useAuth } from '../../state/auth/AuthContext';
import {
  collaborationService, METRIC_LABELS, type BrandProfile, type CollaborationEvaluation, type GoalWeights,
} from '../../services/collaboration/collaborationService';

const CATEGORIES = ['IP', 'Creator', 'Fandom', 'Franchise', 'Character', 'Community', 'Brand'];
const GOAL_LABELS: Record<string, string> = {
  brand_awareness: 'Brand awareness', audience_expansion: 'Audience expansion', revenue: 'Revenue',
  cultural_alignment: 'Cultural alignment', reach_gen_z: 'Reach Gen Z', new_market: 'Enter a new market',
  premium_positioning: 'Strengthen premium positioning', other: 'Other',
};
const EMPTY_BRAND = { brand_name: '', industry: '', primary_offerings: '', target_audience: '', positioning_notes: '', core_values: '', mission: '', primary_markets: '', brand_tone: '' };

function Metric({ label, metric }: { label: string; metric?: { value?: unknown; status: string; inferred?: boolean } }) {
  const value = metric?.value;
  return <div className="rounded-lg border border-app-line bg-app-bg-soft p-3">
    <p className="text-xs text-slate-400">{label}{metric?.inferred ? ' · Inferred' : ''}</p>
    <p className="mt-1 text-sm font-medium text-white">{metric?.status === 'available' ? (Array.isArray(value) ? value.join(', ') : String(value ?? 'Unavailable')) : metric?.status?.replace('_', ' ') || 'Unavailable'}</p>
  </div>;
}

export default function BrandCollaboration() {
  const { profile } = useAuth();
  const canManageBrands = profile?.role === 'admin' || profile?.role === 'analyst';
  const [brands, setBrands] = useState<BrandProfile[]>([]);
  const [goals, setGoals] = useState<GoalWeights[]>([]);
  const [history, setHistory] = useState<CollaborationEvaluation[]>([]);
  const [brandId, setBrandId] = useState(profile?.brand_id || '');
  const [candidate, setCandidate] = useState('');
  const [category, setCategory] = useState('IP');
  const [timeframe, setTimeframe] = useState<7 | 30 | 90>(30);
  const [goal, setGoal] = useState('brand_awareness');
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [otherGoal, setOtherGoal] = useState('');
  const [result, setResult] = useState<CollaborationEvaluation | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingBrand, setEditingBrand] = useState<Record<string, string> | null>(null);

  const reload = async () => {
    const [nextBrands, nextGoals, nextHistory] = await Promise.all([collaborationService.listBrands(), collaborationService.listGoals(), collaborationService.listEvaluations()]);
    setBrands(nextBrands); setGoals(nextGoals); setHistory(nextHistory);
    const fixed = profile?.role === 'client' ? profile.brand_id : brandId || nextBrands[0]?.brand_id;
    if (fixed) setBrandId(fixed);
    const initialGoal = nextGoals.find(item => item.goal === goal) || nextGoals[0];
    if (initialGoal && Object.keys(weights).length === 0) setWeights(initialGoal.weights);
  };

  useEffect(() => {
    let active = true;
    void Promise.all([collaborationService.listBrands(), collaborationService.listGoals(), collaborationService.listEvaluations()])
      .then(([nextBrands, nextGoals, nextHistory]) => {
        if (!active) return;
        setBrands(nextBrands); setGoals(nextGoals); setHistory(nextHistory);
        const fixed = profile?.role === 'client' ? profile.brand_id : nextBrands[0]?.brand_id;
        if (fixed) setBrandId(fixed);
        if (nextGoals[0]) setWeights(nextGoals[0].weights);
      })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Unable to load Collaboration'); });
    return () => { active = false; };
  }, [profile?.brand_id, profile?.role]);
  const selectedBrand = brands.find(item => item.brand_id === brandId);
  const weightTotal = Object.values(weights).reduce((sum, value) => sum + Number(value || 0), 0);
  const valid = Boolean(selectedBrand?.is_complete && candidate.trim() && category && goal && Math.abs(weightTotal - 100) < .01 && (goal !== 'other' || otherGoal.trim()));
  const comparisons = useMemo(() => history.filter(item => compareIds.includes(item.selection_id) && item.status === 'analyzed'), [history, compareIds]);

  const selectGoal = (value: string) => {
    setGoal(value);
    const defaults = goals.find(item => item.goal === value);
    if (defaults) setWeights({ ...defaults.weights });
  };
  const saveBrand = async () => {
    if (!editingBrand) return;
    setBusy(true); setError(null);
    try {
      const saved = editingBrand.brand_id
        ? await collaborationService.updateBrand(editingBrand.brand_id, editingBrand)
        : await collaborationService.createBrand({ ...EMPTY_BRAND, ...editingBrand, industry: editingBrand.industry || null, primary_offerings: editingBrand.primary_offerings || null, target_audience: editingBrand.target_audience || null, positioning_notes: editingBrand.positioning_notes || null, core_values: editingBrand.core_values || null, mission: editingBrand.mission || null, primary_markets: editingBrand.primary_markets || null, brand_tone: editingBrand.brand_tone || null });
      setEditingBrand(null); setBrandId(saved.brand_id); await reload();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save brand'); } finally { setBusy(false); }
  };
  const execute = async () => {
    if (!valid) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const evaluation = await collaborationService.execute({ brand_profile_id: brandId, candidate_name: candidate.trim(), candidate_category: category, timeframe_days: timeframe, collaboration_goal: goal, metric_weights: weights, ...(goal === 'other' ? { other_goal: otherGoal } : {}) });
      setResult(evaluation); await reload();
    } catch (err) { setError(err instanceof Error ? err.message : 'Compatibility evaluation failed'); } finally { setBusy(false); }
  };

  return <div className="space-y-6">
    <div><h2 className="text-2xl font-bold text-white">Brand–IP Collaboration</h2><p className="mt-1 text-sm text-slate-400">Compare a reusable internal brand profile against evidence from an external IP, creator, fandom, franchise, character, community or brand.</p></div>
    {error && <div role="alert" className="rounded-lg border border-red-500/40 bg-red-950/30 p-3 text-sm text-red-200">{error}</div>}

    <div className="grid gap-6 xl:grid-cols-3">
      <Card className="bg-app-surface border-app-line"><CardHeader><CardTitle className="text-white">1. Your Brand</CardTitle><CardDescription className="text-slate-400">Required fields must be complete before execution.</CardDescription></CardHeader><CardContent className="space-y-3">
        <select aria-label="Brand profile" disabled={!canManageBrands} value={brandId} onChange={e => setBrandId(e.target.value)} className="h-10 w-full rounded-md border border-app-line bg-app-bg-soft px-3 text-sm text-white"><option value="">Select brand</option>{brands.map(brand => <option key={brand.brand_id} value={brand.brand_id}>{brand.brand_name}</option>)}</select>
        {selectedBrand && <div className="rounded-lg border border-app-line p-3 text-xs text-slate-300"><p className="font-semibold text-white">{selectedBrand.brand_name}</p><p className="mt-2">Audience: {selectedBrand.target_audience || 'Unavailable'}</p><p>Positioning: {selectedBrand.positioning_notes || 'Unavailable'}</p><p>Values: {selectedBrand.core_values || 'Unavailable'}</p>{selectedBrand.is_complete ? <p className="mt-2 flex items-center gap-1 text-emerald-300"><CheckCircle /> Profile complete</p> : <p className="mt-2 flex items-center gap-1 text-amber-300"><Warning /> Missing: {(selectedBrand.missing_required_fields || ['profile details']).join(', ')}</p>}</div>}
        {canManageBrands && <div className="flex gap-2"><Button variant="outline" className="border-app-line text-slate-200" onClick={() => setEditingBrand(selectedBrand ? Object.fromEntries(Object.entries(selectedBrand).map(([k, v]) => [k, v == null ? '' : String(v)])) : { ...EMPTY_BRAND })}>{selectedBrand ? 'Edit profile' : 'Create profile'}</Button><Button variant="ghost" className="text-slate-300" onClick={() => setEditingBrand({ ...EMPTY_BRAND })}><Plus className="mr-1" /> New</Button></div>}
      </CardContent></Card>

      <Card className="bg-app-surface border-app-line"><CardHeader><CardTitle className="text-white">2. Collaboration Candidate</CardTitle></CardHeader><CardContent className="space-y-3">
        <Input aria-label="Candidate name" placeholder="Candidate name" value={candidate} onChange={e => setCandidate(e.target.value)} className="border-app-line bg-app-bg-soft text-white" />
        <select aria-label="Candidate category" value={category} onChange={e => setCategory(e.target.value)} className="h-10 w-full rounded-md border border-app-line bg-app-bg-soft px-3 text-sm text-white">{CATEGORIES.map(value => <option key={value}>{value}</option>)}</select>
        <select aria-label="Research timeframe" value={timeframe} onChange={e => setTimeframe(Number(e.target.value) as 7 | 30 | 90)} className="h-10 w-full rounded-md border border-app-line bg-app-bg-soft px-3 text-sm text-white"><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option></select>
        <p className="text-xs text-slate-500">Candidate name is the research subject. Manually entered metadata is never treated as measured evidence.</p>
      </CardContent></Card>

      <Card className="bg-app-surface border-app-line"><CardHeader><CardTitle className="text-white">3. Goal & Weights</CardTitle></CardHeader><CardContent className="space-y-3">
        <select aria-label="Collaboration goal" value={goal} onChange={e => selectGoal(e.target.value)} className="h-10 w-full rounded-md border border-app-line bg-app-bg-soft px-3 text-sm text-white">{goals.map(item => <option key={item.goal} value={item.goal}>{GOAL_LABELS[item.goal] || item.goal}</option>)}</select>
        {goal === 'other' && <Input aria-label="Other collaboration goal" value={otherGoal} onChange={e => setOtherGoal(e.target.value)} placeholder="Describe the goal" className="border-app-line bg-app-bg-soft text-white" />}
        {Object.entries(weights).map(([key, value]) => <label key={key} className="grid grid-cols-[1fr_72px] items-center gap-2 text-xs text-slate-300"><span>{METRIC_LABELS[key] || key}</span><Input aria-label={`${METRIC_LABELS[key] || key} weight`} type="number" min={0} max={100} step={1} value={value} onChange={e => setWeights(current => ({ ...current, [key]: Number(e.target.value) }))} className="border-app-line bg-app-bg-soft text-white" /></label>)}
        <p className={Math.abs(weightTotal - 100) < .01 ? 'text-xs text-emerald-300' : 'text-xs text-red-300'}>Total: {weightTotal}% (must equal 100%)</p>
      </CardContent></Card>
    </div>

    {editingBrand && <Card className="bg-app-surface border-app-line"><CardHeader><CardTitle className="text-white">Brand Profile Editor</CardTitle><CardDescription className="text-slate-400">Name, offerings, audience, positioning and values are required.</CardDescription></CardHeader><CardContent className="grid gap-3 md:grid-cols-2">{Object.keys(EMPTY_BRAND).map(key => <label key={key} className="text-xs text-slate-400"><span>{key.replaceAll('_', ' ')}</span><Input value={editingBrand[key] || ''} onChange={e => setEditingBrand(current => ({ ...(current || {}), [key]: e.target.value }))} className="mt-1 border-app-line bg-app-bg-soft text-white" /></label>)}<div className="flex gap-2 md:col-span-2"><Button disabled={busy} onClick={() => void saveBrand()} className="bg-blue-600 text-white"><FloppyDisk className="mr-2" /> Save profile</Button><Button variant="ghost" onClick={() => setEditingBrand(null)} className="text-slate-300">Cancel</Button></div></CardContent></Card>}

    <Button disabled={!valid || busy} onClick={() => void execute()} className="w-full bg-blue-600 py-6 text-base text-white hover:bg-blue-500">{busy ? <><SpinnerGap className="mr-2 animate-spin" /> Researching candidate and checking compatibility…</> : <><ArrowsLeftRight className="mr-2" /> Check Compatibility</>}</Button>

    {result && <Card className="bg-app-surface border-app-line"><CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle className="text-white">{result.brand_name} × {result.candidate_name}</CardTitle><CardDescription className="text-slate-400">Goal: {GOAL_LABELS[result.collaboration_goal]} · {result.reused_research ? 'Compatible stored research reused' : 'New candidate research'}</CardDescription></div><div className="text-right"><p className="text-3xl font-bold text-white">{result.overall_score ?? '—'}</p><p className="text-xs text-slate-400">Goal-specific readiness · {result.recommendation}</p></div></div></CardHeader><CardContent className="space-y-6">
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4"><Metric label="Audience size" metric={result.candidate_metrics.audience_size} /><Metric label="Audience growth" metric={result.candidate_metrics.audience_growth_rate} /><Metric label="Engagement volume" metric={result.candidate_metrics.engagement_volume} /><Metric label="Engagement velocity" metric={result.candidate_metrics.engagement_velocity} /><Metric label="Demographics" metric={result.candidate_metrics.demographics} /><Metric label="Themes" metric={result.candidate_metrics.themes} /><Metric label="Momentum" metric={result.candidate_metrics.momentum} /><div className="rounded-lg border border-app-line bg-app-bg-soft p-3"><p className="text-xs text-slate-400">Sentiment distribution</p><p className="mt-1 text-sm text-white">+{result.candidate_metrics.sentiment_distribution?.positive ?? '—'} / ={result.candidate_metrics.sentiment_distribution?.neutral ?? '—'} / −{result.candidate_metrics.sentiment_distribution?.negative ?? '—'}</p></div></div>
      <div><h3 className="mb-3 font-semibold text-white">Transparent score breakdown</h3><div className="grid gap-3 md:grid-cols-2">{Object.entries(result.component_scores).map(([key, value]) => <div key={key} className="rounded-lg border border-app-line p-3"><div className="flex justify-between text-sm text-slate-200"><span>{METRIC_LABELS[key]}</span><span>{value.score}/100</span></div><div className="mt-2 h-2 overflow-hidden rounded bg-slate-800"><div className="h-full bg-blue-500" style={{ width: `${value.score}%` }} /></div><p className="mt-1 text-xs text-slate-500">Weight {value.weight}% · contribution {value.weighted_score}</p></div>)}</div></div>
      <div className="grid gap-4 md:grid-cols-3"><div><h4 className="text-sm font-semibold text-emerald-300">Strengths</h4><p className="mt-2 text-sm text-slate-300">{result.strengths.join(' · ') || 'Insufficient data'}</p></div><div><h4 className="text-sm font-semibold text-amber-300">Gaps</h4><p className="mt-2 text-sm text-slate-300">{result.weaknesses.join(' · ') || 'No material gap detected'}</p></div><div><h4 className="text-sm font-semibold text-red-300">Risks</h4><p className="mt-2 text-sm text-slate-300">{result.risk_signals.join(' · ') || 'No threshold crossed'}</p></div></div>
      <div className="rounded-xl border border-blue-500/30 bg-blue-950/20 p-4"><h3 className="font-semibold text-white">Vibe Check — Brand–IP Compatibility Summary</h3><ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-300">{result.vibe_check.map((item, index) => <li key={index}>{item.text}<span className="ml-1 text-xs text-slate-500">[{item.evidence_signal_ids?.length ? `${item.evidence_signal_ids.length} evidence signals` : item.metric_references?.join(', ')}]</span></li>)}</ul></div>
      <div className="flex flex-wrap justify-between gap-3 text-xs text-slate-500"><span>Methodology: {result.methodology_version} · Provider: {result.provider_name} · Model: {result.model_version || 'deterministic'}</span><button className="text-blue-300 hover:underline" onClick={() => { const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${result.brand_name}-${result.candidate_name}-collaboration.json`; link.click(); URL.revokeObjectURL(link.href); }}>Export persisted collaboration case</button></div>
    </CardContent></Card>}

    <Card className="bg-app-surface border-app-line"><CardHeader><CardTitle className="text-white">Collaboration History & Multi-candidate Comparison</CardTitle><CardDescription className="text-slate-400">Select previous evaluations to compare their persisted results.</CardDescription></CardHeader><CardContent className="space-y-4">{history.length === 0 ? <p className="text-sm text-slate-400">No previous evaluations.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th className="p-2">Compare</th><th>Brand</th><th>Candidate</th><th>Goal</th><th>Score</th><th>Decision</th></tr></thead><tbody>{history.map(item => <tr key={item.selection_id} className="border-t border-app-line text-slate-300"><td className="p-2"><input type="checkbox" checked={compareIds.includes(item.selection_id)} onChange={e => setCompareIds(current => e.target.checked ? [...current, item.selection_id] : current.filter(id => id !== item.selection_id))} /></td><td>{item.brand_name}</td><td>{item.candidate_name}</td><td>{GOAL_LABELS[item.collaboration_goal]}</td><td>{item.overall_score ?? item.status}</td><td>{item.recommendation || 'Pending'}</td></tr>)}</tbody></table></div>}{comparisons.length > 1 && <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{comparisons.map(item => <div key={item.selection_id} className="rounded-lg border border-app-line p-4"><p className="font-semibold text-white">{item.candidate_name}</p><p className="text-2xl font-bold text-blue-300">{item.overall_score}</p>{Object.entries(item.component_scores).map(([key, value]) => <p key={key} className="mt-1 flex justify-between text-xs text-slate-400"><span>{METRIC_LABELS[key]}</span><span>{value.score}</span></p>)}</div>)}</div>}</CardContent></Card>
  </div>;
}
