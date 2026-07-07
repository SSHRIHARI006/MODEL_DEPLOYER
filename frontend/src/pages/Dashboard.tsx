import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { useStore } from '../store';
import { api } from '../api';
import { ModelCard, type ModelData } from '../components/ModelCard';
import { LayoutDashboard, Key, Wallet, Plus, Copy, CheckCircle } from 'lucide-react';

interface DashboardSummary {
  username: string;
  email: string;
  total_models: number;
  public_models: number;
  wallet_balance: string;
  lifetime_earned: string;
  models: ModelData[];
}

export function Dashboard() {
  const { token, keys, fetchWallet, fetchKeys } = useStore();
  const [activeTab, setActiveTab] = useState<'models' | 'keys' | 'wallet'>('models');
  
  if (!token) return <Navigate to="/login" replace />;

  useEffect(() => {
    fetchWallet();
    fetchKeys();
  }, [fetchWallet, fetchKeys]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      
      <main style={{ flex: 1, maxWidth: 1280, margin: '0 auto', width: '100%', padding: '32px 24px', display: 'flex', gap: 32 }}>
        
        {/* Sidebar Nav */}
        <aside style={{ width: 250, flexShrink: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <NavButton icon={<LayoutDashboard size={18}/>} label="Models" active={activeTab === 'models'} onClick={() => setActiveTab('models')} />
            <NavButton icon={<Key size={18}/>} label="API Keys" active={activeTab === 'keys'} onClick={() => setActiveTab('keys')} />
            <NavButton icon={<Wallet size={18}/>} label="Billing & Wallet" active={activeTab === 'wallet'} onClick={() => setActiveTab('wallet')} />
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

function NavButton({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active: boolean, onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '8px 12px',
        borderRadius: 'var(--radius)',
        background: active ? 'var(--color-surface)' : 'transparent',
        border: active ? '1px solid var(--color-border)' : '1px solid transparent',
        color: active ? 'var(--color-text)' : 'var(--color-text-muted)',
        fontWeight: active ? 600 : 400,
        fontSize: 14,
        cursor: 'pointer',
        textAlign: 'left'
      }}
    >
      {icon} {label}
    </button>
  );
}

// ── Models Sub-view ──────────────────────────────────────────────────────────

function ModelsView() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<DashboardSummary>('/dashboard/summary/')
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading models...</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, borderBottom: '1px solid var(--color-border)', paddingBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>My Models</h2>
        <button style={{ padding: '6px 16px', background: 'var(--color-cta)', color: '#fff', borderRadius: 'var(--radius)', border: '1px solid rgba(27,31,36,0.15)', display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
          <Plus size={16} /> New Model
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
        {data?.models.map(m => <ModelCard key={m.id} model={m} />)}
      </div>
      {data?.models.length === 0 && (
        <div style={{ padding: 48, textAlign: 'center', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
          You haven't uploaded any models yet.
        </div>
      )}
    </div>
  );
}

// ── Keys Sub-view ────────────────────────────────────────────────────────────

function KeysView({ keys, onRefresh }: { keys: any[], onRefresh: () => void }) {
  const [generating, setGenerating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await api.post<any>('/keys/universal/', { name: 'New Key' });
      setNewKey(res.key);
      onRefresh();
    } catch (err) {
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, borderBottom: '1px solid var(--color-border)', paddingBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>Universal API Keys</h2>
        <button onClick={handleGenerate} disabled={generating} style={{ padding: '6px 16px', background: 'var(--color-surface)', color: 'var(--color-text)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
          {generating ? 'Generating...' : 'Generate New Key'}
        </button>
      </div>

      {newKey && (
        <div style={{ padding: 16, border: '1px solid var(--color-cta)', borderRadius: 'var(--radius)', background: '#f6fef8', marginBottom: 24 }}>
          <h4 style={{ color: 'var(--color-cta)', marginBottom: 8, fontSize: 14 }}>New key generated successfully!</h4>
          <p style={{ fontSize: 14, marginBottom: 12, color: 'var(--color-text-muted)' }}>Make sure to copy your key now. You won't be able to see it again!</p>
          <div style={{ display: 'flex', gap: 12 }}>
            <code style={{ flex: 1, padding: '8px 12px', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
              {newKey}
            </code>
            <button onClick={handleCopy} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 16px', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', cursor: 'pointer' }}>
              {copied ? <CheckCircle size={16} color="var(--color-cta)" /> : <Copy size={16} />}
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      <div style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 14 }}>
          <thead style={{ background: 'var(--color-bg)', borderBottom: '1px solid var(--color-border)' }}>
            <tr>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>NAME</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>PREFIX</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>CREATED</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)', textAlign: 'right' }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {keys.filter(k => k.is_active).map(key => (
              <tr key={key.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td style={{ padding: '12px 16px', fontWeight: 500 }}>{key.name}</td>
                <td style={{ padding: '12px 16px', fontFamily: 'var(--font-mono)' }}>{key.prefix}...</td>
                <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)' }}>{new Date(key.created_at).toLocaleDateString()}</td>
                <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                  <button onClick={() => handleDelete(key.id)} style={{ padding: '4px 8px', fontSize: 12, color: 'var(--color-danger)', background: 'transparent', border: '1px solid transparent', cursor: 'pointer' }}>
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
            {keys.filter(k => k.is_active).length === 0 && (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}>No active API keys found.</td></tr>
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
    api.get<any>('/wallet/')
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
    } catch (err) {
      alert('Deposit failed');
    } finally {
      setDepositing(false);
    }
  };

  if (loading) return <div>Loading wallet...</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, borderBottom: '1px solid var(--color-border)', paddingBottom: 16 }}>
        <h2 style={{ fontSize: 24, fontWeight: 600 }}>Billing & Wallet</h2>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 32 }}>
        <div style={{ flex: 1, padding: 24, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
          <div style={{ fontSize: 14, color: 'var(--color-text-muted)', marginBottom: 8, fontWeight: 600 }}>CURRENT BALANCE</div>
          <div style={{ fontSize: 32, fontWeight: 800 }}>{parseFloat(data?.wallet.credit_balance || '0').toFixed(4)}</div>
        </div>
        <div style={{ flex: 1, padding: 24, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
          <div style={{ fontSize: 14, color: 'var(--color-text-muted)', marginBottom: 8, fontWeight: 600 }}>LIFETIME EARNED</div>
          <div style={{ fontSize: 32, fontWeight: 800 }}>{parseFloat(data?.wallet.lifetime_earned || '0').toFixed(4)}</div>
        </div>
      </div>

      <div style={{ marginBottom: 32, padding: 24, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', display: 'flex', gap: 16, alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Add test credits</h3>
          <p style={{ fontSize: 14, color: 'var(--color-text-muted)' }}>Deposit mock credits into your wallet for testing inference.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="number"
            value={depositAmount}
            onChange={e => setDepositAmount(e.target.value)}
            placeholder="Amount"
            style={{ padding: '6px 12px', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)', fontSize: 14, width: 120 }}
          />
          <button onClick={handleDeposit} disabled={depositing} style={{ padding: '6px 16px', background: 'var(--color-cta)', color: '#fff', borderRadius: 'var(--radius)', border: '1px solid rgba(27,31,36,0.15)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
            {depositing ? '...' : 'Deposit'}
          </button>
        </div>
      </div>

      <h3 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Ledger Transactions</h3>
      <div style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 14 }}>
          <thead style={{ background: 'var(--color-bg)', borderBottom: '1px solid var(--color-border)' }}>
            <tr>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>DATE</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>TYPE</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)' }}>DETAILS</th>
              <th style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--color-text-muted)', textAlign: 'right' }}>AMOUNT</th>
            </tr>
          </thead>
          <tbody>
            {data?.transactions.map((tx: any) => (
              <tr key={tx.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                <td style={{ padding: '12px 16px', color: 'var(--color-text-muted)' }}>{new Date(tx.timestamp).toLocaleString()}</td>
                <td style={{ padding: '12px 16px' }}>
                  <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: 12, background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
                    {tx.transaction_type}
                  </span>
                </td>
                <td style={{ padding: '12px 16px' }}>{tx.description || (tx.model_name ? `Inference run on ${tx.model_name}` : '-')}</td>
                <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, color: tx.transaction_type === 'DEPOSIT' || tx.transaction_type === 'PAYOUT' ? 'var(--color-cta)' : 'var(--color-text)' }}>
                  {tx.transaction_type === 'INFERENCE' ? '-' : '+'}{parseFloat(tx.amount).toFixed(4)}
                </td>
              </tr>
            ))}
            {data?.transactions.length === 0 && (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)' }}>No transactions yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
