import { useEffect, useState } from 'react';
import { useParams, Navigate, Link } from 'react-router-dom';
import { api } from '../api';
import { Navbar } from '../components/Navbar';
import { useStore } from '../store';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import SyntaxHighlighter from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { Book, Zap, Settings, Lock, Globe, Terminal, Play, AlertCircle } from 'lucide-react';

interface ModelDetail {
  id: string;
  name: string;
  framework: string;
  task_type: string;
  description: string;
  cost_per_run: string;
  is_public: boolean;
  owner_username: string;
  readme_markdown: string;
  total_versions: number;
  created_at: string;
}

export function ModelRepo() {
  const { namespace, model_name } = useParams();
  const { wallet, username: currentUser } = useStore();
  
  if (!namespace?.startsWith('@')) return <Navigate to="/404" replace />;
  const owner_username = namespace.substring(1);
  
  const [model, setModel] = useState<ModelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'readme' | 'playground' | 'settings'>('readme');

  // Playground state
  const [payload, setPayload] = useState('{\n  "features": [[5.1, 3.5, 1.4, 0.2]]\n}');
  const [output, setOutput] = useState<string>('');
  const [running, setRunning] = useState(false);

  // Settings form state
  const [editDesc, setEditDesc] = useState('');
  const [editReadme, setEditReadme] = useState('');
  const [editCost, setEditCost] = useState('');
  const [editPublic, setEditPublic] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get<ModelDetail>(`/models/@${owner_username}/${model_name}/`)
      .then(res => { 
        setModel(res); 
        setEditDesc(res.description);
        setEditReadme(res.readme_markdown);
        setEditCost(res.cost_per_run);
        setEditPublic(res.is_public);
        setError(null); 
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [owner_username, model_name]);

  const handleRunInference = async () => {
    if (!model) return;
    try {
      JSON.parse(payload);
    } catch {
      setOutput('Error: Invalid JSON payload.');
      return;
    }

    setRunning(true);
    setOutput('Running inference...');
    
    // We assume the user has a universal key if testing here, or we use standard JWT session
    // The backend endpoint `/api/v1/inference/...` needs auth. If JWT works for the UI session, we just call it.
    try {
      const res = await api.post(`/v1/inference/@${owner_username}/${model_name}/`, JSON.parse(payload));
      setOutput(JSON.stringify(res, null, 2));
      // Refresh wallet after successful run
      useStore.getState().fetchWallet();
    } catch (err: any) {
      setOutput(`Error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.patch<ModelDetail>(`/models/@${owner_username}/${model_name}/`, {
        description: editDesc,
        readme_markdown: editReadme,
        cost_per_run: editCost,
        is_public: editPublic
      });
      setModel(res);
      alert("Settings saved successfully!");
    } catch (err: any) {
      alert(`Failed to save settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div><Navbar /><div style={{ padding: 40, textAlign: 'center' }}>Loading repository...</div></div>;
  if (error) return <div><Navbar /><div style={{ padding: 40, textAlign: 'center', color: 'red' }}>{error}</div></div>;
  if (!model) return null;

  const cost = parseFloat(model.cost_per_run);
  const balance = wallet ? parseFloat(wallet.credit_balance) : 0;
  const canRun = balance >= cost;
  const isOwner = currentUser === owner_username;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      
      {/* Repo Header */}
      <div style={{ background: 'var(--color-bg)', borderBottom: '1px solid var(--color-border)', paddingTop: 24 }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 20 }}>
              <Book size={20} color="var(--color-text-muted)" />
              <Link to={`/@${owner_username}`} style={{ color: 'var(--color-accent)', textDecoration: 'none' }}>{owner_username}</Link>
              <span style={{ color: 'var(--color-text-muted)' }}>/</span>
              <span style={{ fontWeight: 600, color: 'var(--color-accent)' }}>{model.name}</span>
              <span style={{ fontSize: 12, padding: '2px 8px', border: '1px solid var(--color-border)', borderRadius: '2em', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                {model.is_public ? <Globe size={12}/> : <Lock size={12}/>}
                {model.is_public ? 'Public' : 'Private'}
              </span>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              {wallet && (
                <div style={{ fontSize: 13, color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  Wallet: <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>{balance.toFixed(4)} credits</span>
                </div>
              )}
              <div style={{ fontSize: 13, border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', padding: '4px 12px', background: 'var(--color-surface)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontWeight: 600 }}>{cost.toFixed(4)}</span> credits / run
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 16 }}>
            <TabButton icon={<Book size={16}/>} label="Readme" active={activeTab === 'readme'} onClick={() => setActiveTab('readme')} />
            <TabButton icon={<Zap size={16}/>} label="Playground" active={activeTab === 'playground'} onClick={() => setActiveTab('playground')} />
            {isOwner && (
              <TabButton icon={<Settings size={16}/>} label="Settings" active={activeTab === 'settings'} onClick={() => setActiveTab('settings')} />
            )}
          </div>
        </div>
      </div>

      <main style={{ flex: 1, maxWidth: 1280, margin: '0 auto', width: '100%', padding: '32px 24px' }}>
        
        {/* README TAB */}
        {activeTab === 'readme' && (
          <div style={{ display: 'flex', gap: 24 }}>
            <div style={{ flex: 1, border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg)', fontWeight: 600, fontSize: 14 }}>
                README.md
              </div>
              <div className="markdown-body" style={{ padding: 32 }}>
                {model.readme_markdown ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({node, inline, className, children, ...props}: any) {
                        const match = /language-(\w+)/.exec(className || '')
                        return !inline && match ? (
                          <SyntaxHighlighter style={github as any} language={match[1]} PreTag="div" {...props}>
                            {String(children).replace(/\n$/, '')}
                          </SyntaxHighlighter>
                        ) : (
                          <code className={className} {...props}>
                            {children}
                          </code>
                        )
                      }
                    }}
                  >
                    {model.readme_markdown}
                  </ReactMarkdown>
                ) : (
                  <div style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>No README provided for this model.</div>
                )}
              </div>
            </div>

            {/* API Snippets Sidebar */}
            <aside style={{ width: 320, flexShrink: 0 }}>
              <div style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg)', fontWeight: 600, fontSize: 14 }}>
                  API Usage
                </div>
                <div style={{ padding: 16 }}>
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--color-text-muted)' }}>cURL</div>
                    <pre style={{ padding: 12, background: 'var(--color-terminal)', color: 'var(--color-terminal-text)', borderRadius: 'var(--radius)', fontSize: 12, overflow: 'auto', margin: 0 }}>
{`curl -X POST \\
  http://localhost:8000/api/v1/inference/@${owner_username}/${model_name}/ \\
  -H "Authorization: Bearer YOUR_UNIVERSAL_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "features": [
      [1.0, 2.0, 3.0]
    ]
  }'`}
                    </pre>
                  </div>
                  
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--color-text-muted)' }}>Python (requests)</div>
                    <pre style={{ padding: 12, background: 'var(--color-terminal)', color: 'var(--color-terminal-text)', borderRadius: 'var(--radius)', fontSize: 12, overflow: 'auto', margin: 0 }}>
{`import requests

url = "http://localhost:8000/api/v1/inference/@${owner_username}/${model_name}/"
headers = {
    "Authorization": "Bearer YOUR_UNIVERSAL_API_KEY",
    "Content-Type": "application/json"
}
data = {
    "features": [[1.0, 2.0, 3.0]]
}

response = requests.post(url, json=data, headers=headers)
print(response.json())`}
                    </pre>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        )}

        {/* PLAYGROUND TAB */}
        {activeTab === 'playground' && (
          <div style={{ display: 'flex', gap: 24, height: '600px' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg)', fontWeight: 600, fontSize: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Request Payload (JSON)</span>
                <button
                  onClick={handleRunInference}
                  disabled={running || !canRun}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '4px 12px', borderRadius: 'var(--radius)',
                    background: canRun ? 'var(--color-cta)' : 'var(--color-bg)',
                    color: canRun ? '#fff' : 'var(--color-text-muted)',
                    border: canRun ? '1px solid rgba(27,31,36,0.15)' : '1px solid var(--color-border)',
                    cursor: canRun && !running ? 'pointer' : 'not-allowed',
                    fontSize: 12, fontWeight: 600
                  }}
                >
                  <Play size={12} /> {running ? 'Running...' : 'Execute'}
                </button>
              </div>
              {!canRun && (
                <div style={{ padding: '8px 16px', background: '#fff8c5', borderBottom: '1px solid #d4a72c', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <AlertCircle size={14} color="#9a6700" />
                  <span style={{ color: '#9a6700' }}>Insufficient credits. Please deposit credits to your wallet.</span>
                </div>
              )}
              <textarea
                value={payload}
                onChange={e => setPayload(e.target.value)}
                style={{ flex: 1, padding: 16, border: 'none', resize: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 13, background: 'transparent' }}
                spellCheck={false}
              />
            </div>
            
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-terminal)', color: 'var(--color-terminal-text)' }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid #30363d', fontWeight: 600, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Terminal size={16} /> Console Output
              </div>
              <pre style={{ flex: 1, padding: 16, overflow: 'auto', margin: 0, fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                {output || 'Ready.'}
              </pre>
            </div>
          </div>
        )}

        {/* SETTINGS TAB */}
        {activeTab === 'settings' && isOwner && (
          <div style={{ maxWidth: 800 }}>
            <h3 style={{ fontSize: 18, marginBottom: 16 }}>Repository Settings</h3>
            <p style={{ color: 'var(--color-text-muted)', fontSize: 14, marginBottom: 24 }}>Update visibility, pricing, and documentation.</p>
            
            <form onSubmit={handleSaveSettings} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div style={{ padding: 24, border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Short Description</label>
                  <input 
                    type="text" 
                    value={editDesc} 
                    onChange={e => setEditDesc(e.target.value)} 
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)', fontSize: 14 }}
                  />
                </div>
                
                <div style={{ marginBottom: 16 }}>
                  <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>README (Markdown)</label>
                  <textarea 
                    value={editReadme} 
                    onChange={e => setEditReadme(e.target.value)}
                    style={{ width: '100%', height: 300, padding: '12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)', fontSize: 14, fontFamily: 'var(--font-mono)', resize: 'vertical' }}
                  />
                </div>
                
                <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Cost per Run (Credits)</label>
                    <input 
                      type="number" 
                      step="0.0001"
                      value={editCost} 
                      onChange={e => setEditCost(e.target.value)} 
                      style={{ width: '100%', padding: '8px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)', fontSize: 14 }}
                    />
                  </div>
                  
                  <div style={{ flex: 1 }}>
                    <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Visibility</label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                      <input 
                        type="checkbox" 
                        checked={editPublic} 
                        onChange={e => setEditPublic(e.target.checked)} 
                      />
                      Make this model public on the marketplace
                    </label>
                  </div>
                </div>
                
                <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'flex-end' }}>
                  <button type="submit" disabled={saving} style={{ padding: '8px 16px', background: 'var(--color-cta)', color: '#fff', borderRadius: 'var(--radius)', border: '1px solid rgba(27,31,36,0.15)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                    {saving ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        )}

      </main>
    </div>
  );
}

function TabButton({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active: boolean, onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 16px',
        background: 'transparent',
        border: 'none',
        borderBottom: active ? '2px solid var(--color-accent)' : '2px solid transparent',
        color: active ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontWeight: active ? 600 : 400,
        fontSize: 14,
        cursor: 'pointer',
      }}
    >
      {icon} {label}
    </button>
  );
}
