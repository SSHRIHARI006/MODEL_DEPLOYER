import { useEffect, useState, useRef, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { useStore } from '../store';
import { api } from '../api';
import { ModelCard, type ModelData } from '../components/ModelCard';
import {
  LayoutDashboard,
  Key,
  Wallet,
  Plus,
  Copy,
  CheckCircle,
  X,
  Upload,
  AlertCircle,
  Square,
  RefreshCw,
  Server,
} from 'lucide-react';

interface DashboardSummary {
  username: string;
  email: string;
  total_models: number;
  public_models: number;
  wallet_balance: string;
  lifetime_earned: string;
  models: ModelData[];
}

interface DeploymentData {
  id: string;
  model_version_id: string;
  status: 'PENDING' | 'BUILDING' | 'RUNNING' | 'FAILED' | 'STOPPED';
  internal_url: string | null;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
}

export function Dashboard() {
  const { token, keys, fetchWallet, fetchKeys } = useStore();
  const [activeTab, setActiveTab] = useState<'models' | 'keys' | 'wallet'>('models');

  useEffect(() => {
    if (token) {
      fetchWallet();
      fetchKeys();
    }
  }, [token, fetchWallet, fetchKeys]);

  if (!token) return <Navigate to="/login" replace />;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      <main
        style={{
          flex: 1,
          maxWidth: 1280,
          margin: '0 auto',
          width: '100%',
          padding: '32px 24px',
          display: 'flex',
          gap: 32,
        }}
      >
        {/* Sidebar Nav */}
        <aside style={{ width: 250, flexShrink: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <NavButton
              icon={<LayoutDashboard size={18} />}
              label="Models & Deployments"
              active={activeTab === 'models'}
              onClick={() => setActiveTab('models')}
            />
            <NavButton
              icon={<Key size={18} />}
              label="API Keys"
              active={activeTab === 'keys'}
              onClick={() => setActiveTab('keys')}
            />
            <NavButton
              icon={<Wallet size={18} />}
              label="Billing & Wallet"
              active={activeTab === 'wallet'}
              onClick={() => setActiveTab('wallet')}
            />
          </div>
        </aside>

        {/* Main Content */}
        <div style={{ flex: 1 }}>
          {activeTab === 'models' && <ModelsView />}
          {activeTab === 'keys' && <KeysView keys={keys} onRefresh={fetchKeys} />}
          {activeTab === 'wallet' && <WalletView onRefresh={fetchWallet} />}
        </div>
      </main>
    </div>
  );
}

function NavButton({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 12px',
        borderRadius: 'var(--radius)',
        background: active ? 'var(--color-surface)' : 'transparent',
        border: active ? '1px solid var(--color-border)' : '1px solid transparent',
        color: active ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontWeight: active ? 600 : 400,
        fontSize: 14,
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      {icon} {label}
    </button>
  );
}

// ── Models & Deployments View (UI-01) ──────────────────────────────────────────

function ModelsView() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [deployments, setDeployments] = useState<DeploymentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const pollCountRef = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSummaryAndDeployments = useCallback(async () => {
    try {
      const [summaryRes, depsRes] = await Promise.all([
        api.get<DashboardSummary>('/dashboard/summary/'),
        api.get<DeploymentData[]>('/deployments/').catch(() => []),
      ]);
      setData(summaryRes);
      setDeployments(depsRes);

      // Check if any deployment is in non-terminal state
      const hasActive = depsRes.some(
        (d) => d.status === 'PENDING' || d.status === 'BUILDING'
      );
      if (hasActive && pollCountRef.current < 30) {
        pollCountRef.current += 1;
        pollTimerRef.current = setTimeout(fetchSummaryAndDeployments, 3000);
      } else {
        pollCountRef.current = 0;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummaryAndDeployments();
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [fetchSummaryAndDeployments]);

  const handleStopDeployment = async (depId: string) => {
    try {
      await api.post(`/deployments/${depId}/stop/`);
      setActionMessage(`Deployment stopped successfully.`);
      setTimeout(() => setActionMessage(null), 4000);
      fetchSummaryAndDeployments();
    } catch (err: any) {
      alert(`Failed to stop deployment: ${err.message}`);
    }
  };

  const handleDeployVersion = async (modelVersionId: string) => {
    try {
      await api.post('/deployments/', { model_version_id: modelVersionId });
      setActionMessage(`Deployment requested. Building model runtime...`);
      setTimeout(() => setActionMessage(null), 4000);
      pollCountRef.current = 0;
      fetchSummaryAndDeployments();
    } catch (err: any) {
      alert(`Deployment failed: ${err.message}`);
    }
  };

  if (loading) return <div>Loading models...</div>;

  return (
    <div>
      {/* Header with Upload CTA */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: 16,
        }}
      >
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 600 }}>My Models</h2>
          <p style={{ fontSize: 14, color: 'var(--color-text-muted)', marginTop: 4 }}>
            Manage models, versions, and active inference deployment runtimes.
          </p>
        </div>
        <button
          onClick={() => setShowUploadModal(true)}
          style={{
            padding: '8px 16px',
            background: 'var(--color-cta)',
            color: '#fff',
            borderRadius: 'var(--radius)',
            border: '1px solid rgba(27,31,36,0.15)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Plus size={16} /> New Model
        </button>
      </div>

      {actionMessage && (
        <div
          style={{
            padding: 12,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-cta)',
            borderRadius: 'var(--radius)',
            marginBottom: 20,
            fontSize: 14,
            color: 'var(--color-text)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <CheckCircle size={16} color="var(--color-cta)" /> {actionMessage}
        </div>
      )}

      {/* Model Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 16,
          marginBottom: 36,
        }}
      >
        {data?.models.map((m) => (
          <ModelCard key={m.id} model={m} />
        ))}
      </div>
      {data?.models.length === 0 && (
        <div
          style={{
            padding: 48,
            textAlign: 'center',
            color: 'var(--color-text-muted)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
            background: 'var(--color-surface)',
            marginBottom: 36,
          }}
        >
          You haven't uploaded any models yet. Click "New Model" to get started.
        </div>
      )}

      {/* Deployments Lifecycle Section (UI-01) */}
      <div style={{ marginTop: 24 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Server size={18} color="var(--color-text-muted)" />
            <h3 style={{ fontSize: 18, fontWeight: 600 }}>Active Deployments</h3>
          </div>
          <button
            onClick={() => fetchSummaryAndDeployments()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              padding: '4px 10px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)',
              cursor: 'pointer',
              color: 'var(--color-text-muted)',
            }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>

        <div
          style={{
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
            background: 'var(--color-surface)',
            overflow: 'hidden',
          }}
        >
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              textAlign: 'left',
              fontSize: 14,
            }}
          >
            <thead
              style={{
                background: 'var(--color-bg)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              <tr>
                <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  DEPLOYMENT ID
                </th>
                <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  STATUS
                </th>
                <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  RUNTIME ENDPOINT / ERROR
                </th>
                <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                  STARTED
                </th>
                <th
                  style={{
                    padding: '12px 16px',
                    fontWeight: 600,
                    color: 'var(--color-text-muted)',
                    textAlign: 'right',
                  }}
                >
                  ACTION
                </th>
              </tr>
            </thead>
            <tbody>
              {deployments.map((dep) => (
                <tr key={dep.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                    {dep.id.slice(0, 8)}...
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <StatusBadge status={dep.status} />
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)', fontSize: 13 }}>
                    {dep.last_error ? (
                      <span style={{ color: 'var(--color-danger)' }}>{dep.last_error}</span>
                    ) : dep.internal_url ? (
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{dep.internal_url}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)' }}>
                    {dep.started_at ? new Date(dep.started_at).toLocaleTimeString() : new Date(dep.created_at).toLocaleTimeString()}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    {dep.status === 'RUNNING' || dep.status === 'BUILDING' ? (
                      <button
                        onClick={() => handleStopDeployment(dep.id)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '4px 8px',
                          fontSize: 12,
                          color: 'var(--color-danger)',
                          background: 'transparent',
                          border: '1px solid var(--color-border)',
                          borderRadius: 'var(--radius)',
                          cursor: 'pointer',
                        }}
                      >
                        <Square size={12} /> Stop
                      </button>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
              {deployments.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}
                  >
                    No deployments created yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Upload Modal (UI-01) */}
      {showUploadModal && (
        <UploadModelModal
          onClose={() => setShowUploadModal(false)}
          onSuccess={(res) => {
            fetchSummaryAndDeployments();
            if (res.model_version_id) {
              handleDeployVersion(res.model_version_id);
            }
          }}
        />
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  let bg = '#eee';
  let color = '#555';

  if (status === 'RUNNING') {
    bg = '#d1f2d9';
    color = '#0e7030';
  } else if (status === 'BUILDING' || status === 'PENDING') {
    bg = '#dbeafe';
    color = '#1e40af';
  } else if (status === 'FAILED') {
    bg = '#fee2e2';
    color = '#991b1b';
  } else if (status === 'STOPPED') {
    bg = '#f3f4f6';
    color = '#6b7280';
  }

  return (
    <span
      style={{
        padding: '3px 8px',
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        background: bg,
        color: color,
      }}
    >
      {status}
    </span>
  );
}

// ── Upload Modal Dialog (UI-01) ───────────────────────────────────────────────

function UploadModelModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: (res: any) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<any>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    if (!e.target.files || e.target.files.length === 0) {
      setFile(null);
      return;
    }
    const selected = e.target.files[0];
    if (!selected.name.endsWith('.zip')) {
      setError('Please select a valid .zip archive.');
      setFile(null);
      return;
    }
    if (selected.size > 50 * 1024 * 1024) {
      setError('File exceeds max allowed size of 50MB.');
      setFile(null);
      return;
    }
    setFile(selected);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please choose a file to upload.');
      return;
    }

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.upload<any>('/models/upload/', formData);
      setUploadSuccess(res);
      onSuccess(res);
    } catch (err: any) {
      setError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          maxWidth: 520,
          width: '90%',
          padding: 24,
          boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 20,
          }}
        >
          <h3 style={{ fontSize: 18, fontWeight: 600 }}>Upload Model Bundle</h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-text-muted)',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: 12,
              background: '#fef2f2',
              border: '1px solid #f87171',
              borderRadius: 'var(--radius)',
              color: '#991b1b',
              fontSize: 14,
              marginBottom: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {uploadSuccess ? (
          <div>
            <div
              style={{
                padding: 16,
                background: '#f0fdf4',
                border: '1px solid #86efac',
                borderRadius: 'var(--radius)',
                color: '#166534',
                fontSize: 14,
                marginBottom: 20,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                Model uploaded successfully!
              </div>
              <div>Model ID: {uploadSuccess.model_id}</div>
              <div>Version: {uploadSuccess.version}</div>
            </div>
            <button
              onClick={onClose}
              style={{
                width: '100%',
                padding: '10px 16px',
                background: 'var(--color-cta)',
                color: '#fff',
                borderRadius: 'var(--radius)',
                border: 'none',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleUpload}>
            <div style={{ marginBottom: 20 }}>
              <label
                style={{
                  display: 'block',
                  fontSize: 14,
                  fontWeight: 600,
                  marginBottom: 8,
                }}
              >
                Model Archive (.zip)
              </label>
              <p style={{ fontSize: 12, color: 'var(--color-text-muted)', marginBottom: 8 }}>
                Must contain <code>model.yaml</code>, requirements file, and model artifacts.
              </p>
              <input
                type="file"
                accept=".zip"
                onChange={handleFileChange}
                disabled={uploading}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                }}
              />
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 12,
              }}
            >
              <button
                type="button"
                onClick={onClose}
                disabled={uploading}
                style={{
                  padding: '8px 16px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={uploading || !file}
                style={{
                  padding: '8px 16px',
                  background: uploading ? '#86efac' : 'var(--color-cta)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 'var(--radius)',
                  fontSize: 14,
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  cursor: uploading ? 'not-allowed' : 'pointer',
                }}
              >
                <Upload size={16} />
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// ── Keys Sub-view ────────────────────────────────────────────────────────────

function KeysView({ keys, onRefresh }: { keys: any[]; onRefresh: () => void }) {
  const [generating, setGenerating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await api.post<any>('/keys/universal/', { name: 'New Key' });
      setNewKey(res.key);
      onRefresh();
    } catch {
      alert('Failed to generate key');
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDelete = async (id: string) => {
    if (confirm('Revoke this key immediately?')) {
      await api.delete(`/keys/universal/${id}/`);
      onRefresh();
    }
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: 16,
        }}
      >
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>Universal API Keys</h2>
        <button
          onClick={handleGenerate}
          disabled={generating}
          style={{
            padding: '6px 16px',
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--color-border)',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {generating ? 'Generating...' : 'Generate New Key'}
        </button>
      </div>

      {newKey && (
        <div
          style={{
            padding: 16,
            border: '1px solid var(--color-cta)',
            borderRadius: 'var(--radius)',
            background: '#f6fef8',
            marginBottom: 24,
          }}
        >
          <h4 style={{ color: 'var(--color-cta)', marginBottom: 8, fontSize: 14 }}>
            New key generated successfully!
          </h4>
          <p style={{ fontSize: 14, marginBottom: 12, color: 'var(--color-text-muted)' }}>
            Make sure to copy your key now. You won't be able to see it again!
          </p>
          <div style={{ display: 'flex', gap: 12 }}>
            <code
              style={{
                flex: 1,
                padding: '8px 12px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
              }}
            >
              {newKey}
            </code>
            <button
              onClick={handleCopy}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '0 16px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
                cursor: 'pointer',
              }}
            >
              {copied ? <CheckCircle size={16} color="var(--color-cta)" /> : <Copy size={16} />}
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      <div
        style={{
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          background: 'var(--color-surface)',
          overflow: 'hidden',
        }}
      >
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            textAlign: 'left',
            fontSize: 14,
          }}
        >
          <thead
            style={{
              background: 'var(--color-bg)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <tr>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                NAME
              </th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                PREFIX
              </th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                CREATED
              </th>
              <th
                style={{
                  padding: '12px 16px',
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  textAlign: 'right',
                }}
              >
                ACTIONS
              </th>
            </tr>
          </thead>
          <tbody>
            {keys
              .filter((k) => k.is_active)
              .map((key) => (
                <tr key={key.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500 }}>{key.name}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)' }}>
                    {key.prefix}...
                  </td>
                  <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)' }}>
                    {new Date(key.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <button
                      onClick={() => handleDelete(key.id)}
                      style={{
                        padding: '4px 8px',
                        fontSize: 12,
                        color: 'var(--color-danger)',
                        background: 'transparent',
                        border: '1px solid transparent',
                        cursor: 'pointer',
                      }}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            {keys.filter((k) => k.is_active).length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}
                >
                  No active API keys found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Wallet Sub-view ──────────────────────────────────────────────────────────

function WalletView({ onRefresh }: { onRefresh: () => void }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [depositAmount, setDepositAmount] = useState('');
  const [depositing, setDepositing] = useState(false);

  useEffect(() => {
    api
      .get<any>('/wallet/')
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  const handleDeposit = async () => {
    if (!depositAmount || isNaN(Number(depositAmount))) return;
    setDepositing(true);
    try {
      await api.post('/wallet/deposit/', { amount: Number(depositAmount) });
      const newData = await api.get<any>('/wallet/');
      setData(newData);
      setDepositAmount('');
      onRefresh();
    } catch {
      alert('Deposit failed');
    } finally {
      setDepositing(false);
    }
  };

  if (loading) return <div>Loading wallet...</div>;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: 16,
        }}
      >
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>Billing & Wallet</h2>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 32 }}>
        <div
          style={{
            flex: 1,
            padding: 24,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
          }}
        >
          <div
            style={{
              fontSize: 14,
              color: 'var(--color-text-muted)',
              marginBottom: 8,
              fontWeight: 600,
            }}
          >
            CURRENT BALANCE
          </div>
          <div style={{ fontSize: 32, fontWeight: 800 }}>
            {parseFloat(data?.wallet.credit_balance || '0').toFixed(4)}
          </div>
        </div>
        <div
          style={{
            flex: 1,
            padding: 24,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
          }}
        >
          <div
            style={{
              fontSize: 14,
              color: 'var(--color-text-muted)',
              marginBottom: 8,
              fontWeight: 600,
            }}
          >
            LIFETIME EARNED
          </div>
          <div style={{ fontSize: 32, fontWeight: 800 }}>
            {parseFloat(data?.wallet.lifetime_earned || '0').toFixed(4)}
          </div>
        </div>
      </div>

      <div
        style={{
          marginBottom: 32,
          padding: 24,
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          display: 'flex',
          gap: 16,
          alignItems: 'center',
        }}
      >
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
            Add test credits
          </h3>
          <p style={{ fontSize: 14, color: 'var(--color-text-muted)' }}>
            Deposit mock credits into your wallet for testing inference.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="number"
            value={depositAmount}
            onChange={(e) => setDepositAmount(e.target.value)}
            placeholder="Amount"
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--color-border)',
              fontSize: 14,
              width: 120,
            }}
          />
          <button
            onClick={handleDeposit}
            disabled={depositing}
            style={{
              padding: '6px 16px',
              background: 'var(--color-cta)',
              color: '#fff',
              borderRadius: 'var(--radius)',
              border: '1px solid rgba(27,31,36,0.15)',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {depositing ? '...' : 'Deposit'}
          </button>
        </div>
      </div>

      <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>
        Ledger Transactions
      </h3>
      <div
        style={{
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius)',
          background: 'var(--color-surface)',
          overflow: 'hidden',
        }}
      >
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            textAlign: 'left',
            fontSize: 14,
          }}
        >
          <thead
            style={{
              background: 'var(--color-bg)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <tr>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                DATE
              </th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                TYPE
              </th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>
                DETAILS
              </th>
              <th
                style={{
                  padding: '12px 16px',
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  textAlign: 'right',
                }}
              >
                AMOUNT
              </th>
            </tr>
          </thead>
          <tbody>
            {data?.transactions.map((tx: any) => (
              <tr key={tx.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)' }}>
                  {new Date(tx.timestamp).toLocaleString()}
                </td>
                <td style={{ padding: '12px 16px' }}>
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: 12,
                      fontSize: 12,
                      background: 'var(--color-bg)',
                      border: '1px solid var(--color-border)',
                    }}
                  >
                    {tx.transaction_type}
                  </span>
                </td>
                <td style={{ padding: '12px 16px' }}>
                  {tx.description ||
                    (tx.model_name ? `Inference run on ${tx.model_name}` : '-')}
                </td>
                <td
                  style={{
                    padding: '12px 16px',
                    textAlign: 'right',
                    fontWeight: 600,
                    color:
                      tx.transaction_type === 'DEPOSIT' ||
                      tx.transaction_type === 'PAYOUT' ||
                      tx.transaction_type === 'REFUND'
                        ? 'var(--color-cta)'
                        : 'var(--color-text)',
                  }}
                >
                  {tx.transaction_type === 'INFERENCE' ? '-' : '+'}
                  {parseFloat(tx.amount).toFixed(4)}
                </td>
              </tr>
            ))}
            {data?.transactions.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}
                >
                  No transactions yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
