import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useDashboardWorkflow } from '../hooks/useDashboardWorkflow';

const TIME_RANGE_OPTIONS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
] as const;

export default function DashboardLayout() {
  const {
    keyword,
    timeRange,
    isLoading,
    trendData,
    narrative,
    collaboration,
    lastRunAt,
    setKeyword,
    setTimeRange,
    runSearch,
    exportSlideDeck,
    exportCaseStudy,
  } = useDashboardWorkflow();

  return (
    <div className="min-h-screen bg-gray-50 p-6 flex flex-col items-center">
      {/* Header & Controls */}
      <div className="w-full max-w-6xl bg-white shadow rounded-lg p-6 mb-6">
        <div className="flex items-center space-x-3 mb-4">
          <div className="h-8 w-8 bg-blue-900 rounded-full flex items-center justify-center text-white font-bold text-xs">PP</div>
          <h1 className="text-3xl font-bold text-gray-900">Project Pluto | Luvcraft Explorer</h1>
        </div>
        <div className="flex space-x-4 items-center">
          <input
            type="text"
            placeholder="Enter Fandom Keyword..."
            className="flex-1 p-2 border border-gray-300 rounded"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <select 
            aria-label="Select Time Range"
            title="Time Range"
            className="p-2 border border-gray-300 rounded"
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value) as 7 | 30 | 90)}
          >
            {TIME_RANGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button 
            onClick={runSearch}
            disabled={isLoading}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Running...' : 'Vibe Check (Run)'}
          </button>
          <button 
            onClick={exportSlideDeck}
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 transition"
          >
            Export Slide Deck
          </button>
          <button 
            onClick={exportCaseStudy}
            className="bg-green-800 text-white px-4 py-2 rounded hover:bg-green-900 transition"
          >
            Export Case Study
          </button>
        </div>
        <p className="mt-3 text-xs text-gray-500">
          {lastRunAt ? `Last run at: ${new Date(lastRunAt).toLocaleString()}` : 'No search has been executed yet.'}
        </p>
      </div>

      {/* Main Charts & Vibe Context */}
      <div className="w-full max-w-6xl grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Trend Graph */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Hype vs Sentiment Trend</h2>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="hype" stroke="#8884d8" activeDot={{ r: 8 }} />
                <Line type="monotone" dataKey="sentiment" stroke="#82ca9d" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Narrative theme extractions */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Data Synthesis & Intelligence</h2>
          <div className="p-4 bg-gray-100 rounded text-gray-700 space-y-2">
            <p><strong>Global Summary:</strong> {narrative.globalSummary}</p>
            <p><strong>Vibe Check:</strong> {narrative.vibeCheck}</p>
            <hr className="my-2 border-gray-300" />
            <h3 className="font-bold text-gray-800">Multi-Dimensional Breakdown:</h3>
            <ul className="list-disc pl-5 text-sm">
                <li><strong>Community:</strong> {narrative.community}</li>
                <li><strong>Trend Momentum:</strong> {narrative.trendMomentum}</li>
                <li><strong>Demand Signals:</strong> {narrative.demandSignals}</li>
            </ul>
            <hr className="my-2 border-gray-300" />
            <p className="text-sm text-red-600 font-semibold">Anomalies Detected: {narrative.anomaly}</p>
            <p className="text-xs text-gray-500">Spam exclusion rate: {narrative.spamExclusionRate}</p>
            <p className="text-xs text-blue-600 mt-2 font-medium">KPI Check: {narrative.kpi}</p>
          </div>
        </div>

        {/* Brand-IP Collaboration Fit Summary (New) */}
        <div className="bg-white shadow rounded-lg p-6 md:col-span-2">
          <h2 className="text-xl font-semibold mb-4">Brand-IP Collaboration Fit</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-200">
              <thead>
                <tr className="bg-gray-100 text-left text-sm uppercase text-gray-600">
                  <th className="py-2 px-4 border-b">Candidate / IP</th>
                  <th className="py-2 px-4 border-b">Category</th>
                  <th className="py-2 px-4 border-b">Audience Growth</th>
                  <th className="py-2 px-4 border-b">Collaboration Score</th>
                  <th className="py-2 px-4 border-b">Recommendation</th>
                </tr>
              </thead>
              <tbody className="text-sm text-gray-700">
                {collaboration.map((candidate) => (
                  <tr key={candidate.name}>
                    <td className="py-2 px-4 border-b font-medium">{candidate.name}</td>
                    <td className="py-2 px-4 border-b">{candidate.category}</td>
                    <td className={`py-2 px-4 border-b ${candidate.audienceGrowth.startsWith('+') ? 'text-green-600' : 'text-red-600'}`}>
                      {candidate.audienceGrowth}
                    </td>
                    <td className="py-2 px-4 border-b">{candidate.collaborationScore} / 100</td>
                    <td className={`py-2 px-4 border-b font-bold ${candidate.collaborationScore >= 60 ? 'text-green-600' : 'text-red-600'}`}>
                      {candidate.recommendation}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
