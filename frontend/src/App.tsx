import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import AssistantPage from './pages/AssistantPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import AnalyticsPage from './pages/AnalyticsPage';
import SettingsPage from './pages/SettingsPage';
import { getHealth, getModels, getConversations, createConversation, deleteConversation } from './services/api';
import type { HealthStatus, ModelInfo, Conversation } from './types';

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState('gemini');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [draftInput, setDraftInput] = useState('');
  const [draftMessages, setDraftMessages] = useState<any[]>([]);

  const fetchStatus = async () => {
    try {
      const [healthRes, modelsRes, convsRes] = await Promise.allSettled([
        getHealth(),
        getModels(),
        getConversations(),
      ]);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (modelsRes.status === 'fulfilled') setModels(modelsRes.value.models);
      if (convsRes.status === 'fulfilled') setConversations(convsRes.value.conversations || []);
    } catch (e) {
      console.error('Failed to fetch status:', e);
    }
  };

  useEffect(() => {
    fetchStatus();
    const handleStorage = (e: StorageEvent) => {
      if (e.key === 'nexus_gemini_key_updated') {
        fetchStatus();
      }
    };
    const handleLocalEvent = () => fetchStatus();

    window.addEventListener('storage', handleStorage);
    window.addEventListener('nexus_status_updated', handleLocalEvent);
    const interval = setInterval(fetchStatus, 15000);

    return () => {
      window.removeEventListener('storage', handleStorage);
      window.removeEventListener('nexus_status_updated', handleLocalEvent);
      clearInterval(interval);
    };
  }, []);


  const handleNewChat = async () => {
    try {
      const newConv = await createConversation('New Conversation');
      setConversations(prev => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      setDraftInput('');
      setDraftMessages([]);
    } catch (e) {
      console.error('Failed to create new conversation:', e);
    }
  };

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (activeConversationId === id) {
        setActiveConversationId(null);
        setDraftInput('');
        setDraftMessages([]);
      }
    } catch (e) {
      console.error('Failed to delete conversation:', e);
    }
  };

  return (
    <BrowserRouter>
      <div className="flex h-screen bg-[#E4E2DD] text-[#1E1E1E] overflow-hidden">
        {/* Mobile overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 bg-black/60 z-40 lg:hidden"
               onClick={() => setSidebarOpen(false)} />
        )}

        <Sidebar
          health={health}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={(id) => setActiveConversationId(id)}
          onNewChat={handleNewChat}
          onDeleteConversation={handleDeleteConversation}
        />

        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Mobile header */}
          <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-white/5">
            <button onClick={() => setSidebarOpen(true)}
                    className="btn-ghost p-2" aria-label="Open menu">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <span className="font-semibold text-indigo-400">NEXUS</span>
          </div>

          <Routes>
            <Route path="/" element={<Navigate to="/assistant" replace />} />
            <Route path="/assistant" element={
              <AssistantPage
                models={models}
                selectedModel={selectedModel}
                onModelChange={setSelectedModel}
                activeConversationId={activeConversationId}
                setActiveConversationId={setActiveConversationId}
                onConversationUpdated={fetchStatus}
                draftInput={draftInput}
                setDraftInput={setDraftInput}
                draftMessages={draftMessages}
                setDraftMessages={setDraftMessages}
              />
            } />
            <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/settings" element={<SettingsPage health={health} onStatusUpdated={fetchStatus} />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}


export default App;
