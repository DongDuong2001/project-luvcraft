import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

// Mocked Trend Data for boilerplate
const mockTrendData = [
  { date: '2023-10-01', hype: 400, sentiment: 60 },
  { date: '2023-10-02', hype: 600, sentiment: 65 },
  { date: '2023-10-03', hype: 500, sentiment: 50 },
];

export default function DashboardLayout() {
  const [keyword, setKeyword] = useState<string>('');
  const [timeRange, setTimeRange] = useState<number>(7); // Days: 7, 30, 90

  const handleSearch = () => {
    // Dispatch query to FastAPI backend to trigger Celery workers
    console.log(`Triggering async collection for "${keyword}" over ${timeRange} days`);
  };

  const handleExportSlideDeck = () => {
    // Trigger download of Auto-Generated Executive Slide Deck
    console.log("Exporting Executive Statistical Slide Deck (PDF)...");
  };

  const handleExportCaseStudy = () => {
    // Trigger download of Structured Case Study Report
    console.log("Exporting Structured Case Study Report (PDF)...");
  };

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
            onChange={(e) => setTimeRange(Number(e.target.value))}
          >
            <option value={7}>Last 7 Days</option>
            <option value={30}>Last 30 Days</option>
            <option value={90}>Last 90 Days</option>
          </select>
          <button 
            onClick={handleSearch} 
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition"
          >
            Vibe Check (Run)
          </button>
          <button 
            onClick={handleExportSlideDeck} 
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 transition"
          >
            Export Slide Deck
          </button>
          <button 
            onClick={handleExportCaseStudy} 
            className="bg-green-800 text-white px-4 py-2 rounded hover:bg-green-900 transition"
          >
            Export Case Study
          </button>
        </div>
      </div>

      {/* Main Charts & Vibe Context */}
      <div className="w-full max-w-6xl grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Trend Graph */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Hype vs Sentiment Trend</h2>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mockTrendData}>
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
            <p><strong>Global Summary:</strong> Positive Sentiment (Confidence: 85%)</p>
            <p><strong>Vibe Check:</strong> Cautiously Optimistic. Community is heavily invested in lore expansion.</p>
            <hr className="my-2 border-gray-300" />
            <h3 className="font-bold text-gray-800">Multi-Dimensional Breakdown:</h3>
            <ul className="list-disc pl-5 text-sm">
                <li><strong>Community:</strong> Fans & casual users (Low toxicity)</li>
                <li><strong>Trend Momentum:</strong> Upward (Crossover theories emerging)</li>
                <li><strong>Demand Signals:</strong> Missing merchandise / collectibles</li>
            </ul>
            <hr className="my-2 border-gray-300" />
            <p className="text-sm text-red-600 font-semibold">🚨 Anomalies Detected: Sudden 300% Engagement Spike (Factor: Viral Video)</p>
            <p className="text-xs text-gray-500">Spam exclusion rate: 5.2%</p>
            <p className="text-xs text-blue-600 mt-2 font-medium">KPI Check: End-to-End time 2.1m | Active Sources: 6 (Validated) | Cost: $0.04</p>
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
                <tr>
                  <td className="py-2 px-4 border-b font-medium">Competitor IP Alpha</td>
                  <td className="py-2 px-4 border-b">Franchise</td>
                  <td className="py-2 px-4 border-b text-green-600">+12%</td>
                  <td className="py-2 px-4 border-b">88 / 100</td>
                  <td className="py-2 px-4 border-b text-green-600 font-bold">Proceed</td>
                </tr>
                <tr>
                  <td className="py-2 px-4 border-b font-medium">Influencer Beta</td>
                  <td className="py-2 px-4 border-b">Creator</td>
                  <td className="py-2 px-4 border-b text-red-600">-4%</td>
                  <td className="py-2 px-4 border-b">45 / 100</td>
                  <td className="py-2 px-4 border-b text-red-600 font-bold">Avoid (High Risk)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
