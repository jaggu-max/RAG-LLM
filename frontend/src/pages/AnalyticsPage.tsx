import { useState, useEffect } from 'react';
import { BarChart3, Clock, FileText, Shield, MessageSquare, Database } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { getStats } from '../services/api';
import type { StatsData } from '../types';

export default function AnalyticsPage() {
  const [stats, setStats] = useState<StatsData | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(console.error);
  }, []);

  if (!stats) {
    return (
      <div className="flex-1 flex items-center justify-center font-mono font-bold text-sm text-[#1E1E1E]/60 uppercase">
        Loading analytics metrics...
      </div>
    );
  }

  const COLORS = ['#DB4A2B', '#F8A348', '#FF89A9', '#1E1E1E', '#9333ea', '#2563eb', '#059669'];

  const formatSize = (bytes: number) => {
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(1) + ' GB';
  };

  const typeData = stats.documents_by_type.map(d => ({
    name: d.file_type.toUpperCase(),
    value: d.count,
  }));

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 bg-[#E4E2DD] text-[#1E1E1E] slide-up">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6 pb-4 border-b-2 border-[#1E1E1E]">
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-white bg-[#1E1E1E] px-2 py-0.5 border border-[#1E1E1E]">METRICS</span>
          <h1 className="font-display text-2xl font-bold tracking-tight text-[#1E1E1E] mt-1">Analytics Dashboard</h1>
          <p className="font-sans text-xs font-medium text-[#1E1E1E]/70">RAG pipeline retrieval latency, indexing throughput, and confidence metrics</p>
        </div>

        {/* Metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Documents', value: stats.total_documents, icon: Database, bg: 'bg-white' },
            { label: 'Total Chunks', value: stats.total_chunks.toLocaleString(), icon: FileText, bg: 'bg-[#DB4A2B] text-white' },
            { label: 'Total Queries', value: stats.total_queries, icon: MessageSquare, bg: 'bg-[#F8A348] text-[#1E1E1E]' },
            { label: 'Dataset Size', value: formatSize(stats.dataset_size_bytes), icon: Database, bg: 'bg-white' },
          ].map(({ label, value, icon: Icon, bg }) => (
            <div key={label} className={`${bg} border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-4`}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4" />
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider">{label}</span>
              </div>
              <p className="font-display text-2xl font-bold leading-none">{value}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {[
            { label: 'Avg Confidence', value: `${Math.round(stats.avg_confidence * 100)}%`, icon: Shield, bg: 'bg-white' },
            { label: 'Avg Latency', value: `${Math.round(stats.avg_response_time_ms)} ms`, icon: Clock, bg: 'bg-white' },
            { label: 'Indexed', value: stats.indexed_documents, icon: FileText, bg: 'bg-[#DB4A2B] text-white' },
            { label: 'Failed', value: stats.failed_documents, icon: FileText, bg: 'bg-[#FF89A9] text-[#1E1E1E]' },
          ].map(({ label, value, icon: Icon, bg }) => (
            <div key={label} className={`${bg} border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-4`}>
              <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4" />
                <span className="font-mono text-[10px] font-bold uppercase tracking-wider">{label}</span>
              </div>
              <p className="font-display text-2xl font-bold leading-none">{value}</p>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Documents by Type — Bar Chart */}
          {typeData.length > 0 && (
            <div className="bg-white border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] p-5">
              <h3 className="font-display text-base font-bold text-[#1E1E1E] mb-4 flex items-center gap-2 uppercase tracking-tight">
                <BarChart3 className="w-4 h-4 text-[#DB4A2B]" />
                Documents by Extension
              </h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={typeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E1E1E" strokeOpacity={0.15} />
                  <XAxis dataKey="name" tick={{ fill: '#1E1E1E', fontSize: 11, fontWeight: 'bold' }} axisLine={{ stroke: '#1E1E1E' }} />
                  <YAxis tick={{ fill: '#1E1E1E', fontSize: 11, fontWeight: 'bold' }} axisLine={{ stroke: '#1E1E1E' }} />
                  <Tooltip contentStyle={{ background: '#1E1E1E', border: '2px solid #1E1E1E', color: '#E4E2DD', fontWeight: 'bold' }} />
                  <Bar dataKey="value" fill="#DB4A2B" radius={[0, 0, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Distribution — Pie Chart */}
          {typeData.length > 0 && (
            <div className="bg-white border-2 border-[#1E1E1E] shadow-[6px_6px_0px_#1E1E1E] p-5">
              <h3 className="font-display text-base font-bold text-[#1E1E1E] mb-4 flex items-center gap-2 uppercase tracking-tight">
                <Database className="w-4 h-4 text-[#DB4A2B]" />
                File Distribution
              </h3>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={typeData}
                    cx="50%" cy="50%"
                    innerRadius={50} outerRadius={85}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {typeData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#1E1E1E" strokeWidth={2} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1E1E1E', border: '2px solid #1E1E1E', color: '#E4E2DD', fontWeight: 'bold' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
