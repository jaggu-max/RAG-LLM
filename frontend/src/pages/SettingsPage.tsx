import { useState } from 'react';
import { Settings as SettingsIcon, Circle, CheckCircle, AlertCircle, Key, RefreshCw, Eye, EyeOff, Save } from 'lucide-react';
import { testGeminiKey, saveGeminiKey } from '../services/api';
import type { HealthStatus } from '../types';

interface Props {
  health: HealthStatus | null;
  onStatusUpdated?: () => void;
}

export default function SettingsPage({ health, onStatusUpdated }: Props) {
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusBadge, setStatusBadge] = useState<{ status: string; message: string; valid: boolean } | null>(null);

  const notifyTabSync = () => {
    try {
      localStorage.setItem('nexus_gemini_key_updated', Date.now().toString());
      window.dispatchEvent(new Event('nexus_status_updated'));
    } catch (e) {
      console.error(e);
    }
  };

  const handleTestKey = async () => {
    setTesting(true);
    try {
      const res = await testGeminiKey(apiKeyInput.trim() || undefined);
      setStatusBadge({ status: res.status, message: res.message, valid: res.valid });
      onStatusUpdated?.();
      notifyTabSync();
    } catch (err: any) {
      setStatusBadge({
        status: 'Invalid Key',
        message: err.response?.data?.detail || 'Invalid Gemini API key. Please check your key.',
        valid: false,
      });
      onStatusUpdated?.();
      notifyTabSync();
    } finally {
      setTesting(false);
    }
  };

  const handleSaveKey = async () => {
    if (!apiKeyInput.trim()) return;
    setSaving(true);
    try {
      const res = await saveGeminiKey(apiKeyInput.trim());
      setStatusBadge({ status: res.status, message: res.message, valid: res.valid });
      onStatusUpdated?.();
      notifyTabSync();
    } catch (err: any) {
      setStatusBadge({
        status: 'Invalid Key',
        message: err.response?.data?.detail || 'Invalid Gemini API key. Could not save.',
        valid: false,
      });
      onStatusUpdated?.();
      notifyTabSync();
    } finally {
      setSaving(false);
    }
  };


  // Evaluate readiness accurately: valid from test/save takes priority, otherwise use backend health
  const isGeminiReady = statusBadge ? statusBadge.valid : (health?.gemini === 'ready');

  const getStatusLabel = () => {
    if (isGeminiReady) return 'READY (CONNECTED)';
    if (statusBadge?.status === 'Quota Exceeded') return 'QUOTA EXCEEDED (OFFLINE)';
    if (statusBadge?.status === 'Invalid API Key') return 'INVALID API KEY (OFFLINE)';
    return 'OFFLINE (NOT CONFIGURED)';
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6 bg-[#E4E2DD] text-[#1E1E1E] slide-up">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-6 pb-4 border-b-2 border-[#1E1E1E]">
          <span className="font-mono text-xs font-bold uppercase tracking-widest text-white bg-[#1E1E1E] px-2 py-0.5 border border-[#1E1E1E]">CONFIG</span>
          <h1 className="font-display text-2xl font-bold tracking-tight text-[#1E1E1E] mt-1">System Settings</h1>
          <p className="font-sans text-xs font-medium text-[#1E1E1E]/70">Configure LLM providers, API keys, and RAG pipeline parameters</p>
        </div>

        {/* Gemini API Key Panel */}
        <Section title="Gemini Provider Configuration">
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-6 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="font-mono text-xs font-bold text-[#1E1E1E] uppercase tracking-wider flex items-center gap-2">
                  <Key className="w-4 h-4 text-[#DB4A2B]" />
                  Gemini API Key
                </label>
                {/* Dynamic Green / Red Status Dot Indicator */}
                <div className="flex items-center gap-2">
                  <span className={`w-3 h-3 rounded-full border border-[#1E1E1E] shadow-[1px_1px_0px_#1E1E1E] ${
                    isGeminiReady ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'
                  }`} />
                  <span className={`font-mono text-xs font-bold uppercase px-2 py-0.5 border border-[#1E1E1E] ${
                    isGeminiReady ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
                  }`}>
                    {getStatusLabel()}
                  </span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-2.5">
                <div className="relative flex-1">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKeyInput}
                    onChange={e => setApiKeyInput(e.target.value)}
                    placeholder="Paste your new Gemini API Key here (Google AI Studio)..."
                    className="w-full bg-[#E4E2DD] border-2 border-[#1E1E1E] px-3 py-2 text-xs font-mono font-bold text-[#1E1E1E] shadow-[2px_2px_0px_#1E1E1E] focus:outline-none focus:border-[#DB4A2B] pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#1E1E1E]/60 hover:text-[#1E1E1E]"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleTestKey}
                    disabled={testing}
                    className="btn-secondary px-4 py-2 text-xs uppercase tracking-wider flex items-center gap-2"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
                    Test Connection
                  </button>

                  <button
                    type="button"
                    onClick={handleSaveKey}
                    disabled={saving || !apiKeyInput.trim()}
                    className="btn-primary px-4 py-2 text-xs uppercase tracking-wider flex items-center gap-2"
                  >
                    <Save className="w-3.5 h-3.5" />
                    Save Key
                  </button>
                </div>
              </div>
            </div>

            {/* Connection status result box */}
            {statusBadge && (
              <div className={`flex items-start gap-2.5 p-3.5 border-2 border-[#1E1E1E] font-mono text-xs font-bold ${
                statusBadge.valid
                  ? 'bg-emerald-100 text-emerald-950 border-emerald-900'
                  : 'bg-red-100 text-red-950 border-red-900'
              }`}>
                {statusBadge.valid ? (
                  <CheckCircle className="w-4 h-4 flex-shrink-0 text-emerald-700 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-700 mt-0.5" />
                )}
                <div>
                  <span className="uppercase font-bold tracking-wider">{statusBadge.status}: </span>
                  <span className="font-medium">{statusBadge.message}</span>
                  {!statusBadge.valid && (
                    <p className="mt-1 text-[11px] font-sans font-bold text-red-800">
                      ⚠️ Please enter a new, valid Gemini API key from Google AI Studio above and click [ Save Key ].
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </Section>

        {/* System Nodes Status Grid */}
        <Section title="System Node Metrics" className="mt-8">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {health && Object.entries(health).map(([key, val]) => {
              // Override gemini display if statusBadge status exists
              let displayVal = val;
              if (key === 'gemini' && statusBadge) {
                displayVal = statusBadge.valid ? 'ready' : (statusBadge.status === 'Quota Exceeded' ? 'quota_exceeded' : 'offline');
              }

              const isOnline = ['online', 'ready', 'running'].includes(displayVal);
              const isOffline = ['offline', 'failed', 'not_configured', 'quota_exceeded'].includes(displayVal);
              return (
                <div key={key} className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] px-4 py-3 flex items-center justify-between">
                  <span className="font-mono text-xs font-bold uppercase tracking-wider text-[#1E1E1E]/80">{key.replace(/_/g, ' ')}</span>
                  <span className={`flex items-center gap-1.5 px-2 py-0.5 border border-[#1E1E1E] font-mono text-[10px] font-bold uppercase ${
                    isOnline ? 'bg-emerald-600 text-white' : isOffline ? 'bg-red-600 text-white' : 'bg-[#F8A348] text-[#1E1E1E]'
                  }`}>
                    <Circle className="w-1.5 h-1.5 fill-current" />
                    {displayVal === 'not_configured' ? 'UNCONFIGURED' : displayVal.replace(/_/g, ' ').toUpperCase()}
                  </span>
                </div>
              );
            })}
          </div>
        </Section>

        {/* RAG Pipeline Parameters */}
        <Section title="RAG Pipeline Architecture" className="mt-8">
          <div className="bg-white border-2 border-[#1E1E1E] shadow-[4px_4px_0px_#1E1E1E] p-4 divide-y-2 divide-[#1E1E1E]/20">
            <ConfigRow label="Gemini Model Management" value="Model-Agnostic (Dynamic Discovery)" />
            <ConfigRow label="Local Qwen Endpoint" value="http://127.0.0.1:1234/v1" />
            <ConfigRow label="Vector Embedding Model" value="all-MiniLM-L6-v2 (384-dim)" />
            <ConfigRow label="Retrieval Strategy" value="Hybrid (Semantic 0.7 + Keyword FTS 0.3)" />
            <ConfigRow label="Top-K Candidate Retrieval" value="10 Chunks -> Top 5 Reranked" />
            <ConfigRow label="Chunking Configuration" value="800 Chars • 120 Overlap" />
            <ConfigRow label="Reranker Model" value="ms-marco-MiniLM-L-6-v2" />
            <ConfigRow label="Confidence Threshold" value="70% Similarity Cutoff" />
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <h2 className="font-display text-sm font-bold uppercase tracking-wider text-[#1E1E1E] mb-3 flex items-center gap-2">
        <SettingsIcon className="w-4 h-4 text-[#DB4A2B]" />
        {title}
      </h2>
      {children}
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 px-2 font-mono text-xs">
      <span className="font-bold text-[#1E1E1E]/70">{label}</span>
      <span className="font-bold text-[#1E1E1E] bg-[#E4E2DD] px-2 py-0.5 border border-[#1E1E1E]">{value}</span>
    </div>
  );
}
