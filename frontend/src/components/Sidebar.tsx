import { NavLink } from 'react-router-dom';
import { MessageSquare, Database, BarChart3, Settings, X, Zap, Circle, Plus, Trash2 } from 'lucide-react';
import type { HealthStatus, Conversation } from '../types';

interface Props {
  health: HealthStatus | null;
  isOpen: boolean;
  onClose: () => void;
  conversations?: Conversation[];
  activeConversationId?: string | null;
  onSelectConversation?: (id: string) => void;
  onNewChat?: () => void;
  onDeleteConversation?: (id: string) => void;
}

const navItems = [
  { to: '/assistant', label: 'Assistant', icon: MessageSquare },
  { to: '/knowledge-base', label: 'Knowledge Base', icon: Database },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar({
  health,
  isOpen,
  onClose,
  conversations = [],
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}: Props) {
  return (
    <aside className={`
      fixed lg:static inset-y-0 left-0 z-50
      w-64 border-r-2 border-[#1E1E1E] bg-[#E4E2DD] text-[#1E1E1E]
      flex flex-col transition-transform duration-300 ease-in-out
      ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
    `}>
      {/* Header */}
      <div className="px-5 py-5 flex items-center justify-between border-b-2 border-[#1E1E1E]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-[#DB4A2B] border-2 border-[#1E1E1E]
                          flex items-center justify-center shadow-[3px_3px_0px_#1E1E1E]">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-display font-bold text-lg leading-none tracking-tighter text-[#1E1E1E]">NEXUS</h1>
            <p className="font-mono text-[9px] font-bold tracking-widest text-[#DB4A2B] uppercase mt-0.5">Swiss RAG Engine</p>
          </div>
        </div>
        <button onClick={onClose} className="lg:hidden btn-ghost p-1" aria-label="Close sidebar">
          <X className="w-4 h-4 text-[#1E1E1E]" />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={() => {
            onNewChat?.();
            onClose();
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-[#DB4A2B] hover:bg-[#c43e21] text-white border-2 border-[#1E1E1E] shadow-[3px_3px_0px_#1E1E1E] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none font-bold text-xs transition-all duration-150 uppercase tracking-wider"
        >
          <Plus className="w-4 h-4 stroke-[3]" />
          New Chat
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-3 py-2 space-y-1 border-b-2 border-[#1E1E1E]">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) => `
              flex items-center gap-3 px-3 py-2 border-2 text-xs font-bold uppercase tracking-wider
              transition-all duration-150
              ${isActive
                ? 'bg-[#1E1E1E] text-[#E4E2DD] border-[#1E1E1E] shadow-[3px_3px_0px_#DB4A2B]'
                : 'bg-white/40 text-[#1E1E1E] border-[#1E1E1E]/20 hover:border-[#1E1E1E] hover:bg-white'
              }
            `}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Chat History List */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1.5">
        <p className="px-2 font-mono text-[10px] font-bold tracking-widest text-[#1E1E1E]/60 uppercase mb-2">Saved History</p>
        {conversations.length === 0 ? (
          <p className="px-2 text-xs text-[#1E1E1E]/50 italic">No saved chats</p>
        ) : (
          conversations.map(c => {
            const isActive = c.id === activeConversationId;
            return (
              <div
                key={c.id}
                onClick={() => {
                  onSelectConversation?.(c.id);
                  onClose();
                }}
                className={`group flex items-center justify-between px-3 py-2 border-2 text-xs cursor-pointer transition-all duration-150 ${
                  isActive
                    ? 'bg-[#DB4A2B] text-white border-[#1E1E1E] font-bold shadow-[2px_2px_0px_#1E1E1E]'
                    : 'bg-white/60 border-[#1E1E1E]/20 text-[#1E1E1E] hover:border-[#1E1E1E] hover:bg-white'
                }`}
              >
                <div className="flex items-center gap-2 truncate flex-1 min-w-0 pr-1">
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{c.title || 'Conversation'}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation?.(c.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-[#1E1E1E] hover:text-white transition-opacity"
                  title="Delete chat"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* System Status */}
      <div className="p-4 border-t-2 border-[#1E1E1E] bg-[#1E1E1E]/5">
        <p className="font-mono text-[9px] font-bold tracking-widest text-[#1E1E1E]/60 uppercase mb-2.5">System Nodes</p>
        <div className="space-y-2">
          <StatusRow label="Backend API" status={health?.backend || 'online'} />
          <StatusRow label="Gemini AI" status={health?.gemini || 'ready'} />
          <StatusRow label="Local Qwen" status={health?.lmstudio || 'ready'} extra="Local" />
        </div>
      </div>
    </aside>
  );
}

function StatusRow({ label, status, extra }: { label: string; status?: string; extra?: string }) {
  const normalizedStatus = (status || 'ready').toLowerCase();
  const isOnline = ['online', 'ready', 'running', 'ok'].includes(normalizedStatus);
  const isOffline = ['offline', 'error', 'failed'].includes(normalizedStatus);

  return (
    <div className="flex items-center justify-between text-xs font-mono font-bold">
      <span className="text-[#1E1E1E]/70">{label}</span>
      <span className={`flex items-center gap-1.5 px-1.5 py-0.5 border border-[#1E1E1E] text-[10px] uppercase ${
        isOnline ? 'bg-[#DB4A2B] text-white' : isOffline ? 'bg-black text-white' : 'bg-[#F8A348] text-[#1E1E1E]'
      }`}>
        <Circle className="w-1.5 h-1.5 fill-current" />
        {extra || (isOnline ? 'READY' : normalizedStatus.toUpperCase())}
      </span>
    </div>
  );
}
