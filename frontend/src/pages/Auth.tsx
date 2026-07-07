import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../api';
import { useStore } from '../store';
import { Box } from 'lucide-react';

export function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useStore();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const res = await api.post<any>('/auth/login/', { email, password });
      
      // We don't get the username back from standard JWT token obtain pair view,
      // but in a real scenario we'd decode the JWT or fetch user details.
      // For this spec, we'll fetch dashboard summary to get the username.
      localStorage.setItem('token', res.access); // Temporarily store to let api client work
      
      const dashboard = await api.get<any>('/dashboard/summary/');
      setAuth(res.access, dashboard.username);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed');
      localStorage.removeItem('token');
    } finally {
      setLoading(false);
    }
  };

  return <AuthLayout title="Sign in to Model Deployer" error={error}>
    <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Email address</label>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} required style={inputStyle} />
      </div>
      <div>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required style={inputStyle} />
      </div>
      <button type="submit" disabled={loading} style={btnStyle}>
        {loading ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
    <div style={{ marginTop: 24, textAlign: 'center', fontSize: 14, padding: 16, border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
      New to Model Deployer? <Link to="/register">Create an account</Link>.
    </div>
  </AuthLayout>;
}

export function Register() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useStore();
  const navigate = useNavigate();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      // 1. Register
      await api.post('/auth/register/', { email, username, password });
      // 2. Login to get token
      const res = await api.post<any>('/auth/login/', { email, password });
      setAuth(res.access, username);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return <AuthLayout title="Create your account" error={error}>
    <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Username</label>
        <input type="text" value={username} onChange={e => setUsername(e.target.value)} required pattern="^[a-zA-Z0-9_-]+$" style={inputStyle} placeholder="my_namespace" />
      </div>
      <div>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Email address</label>
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} required style={inputStyle} />
      </div>
      <div>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Password</label>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} style={inputStyle} />
      </div>
      <button type="submit" disabled={loading} style={btnStyle}>
        {loading ? 'Creating account...' : 'Create account'}
      </button>
    </form>
    <div style={{ marginTop: 24, textAlign: 'center', fontSize: 14, padding: 16, border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
      Already have an account? <Link to="/login">Sign in</Link>.
    </div>
  </AuthLayout>;
}

// ── Shared Layout ────────────────────────────────────────────────────────────

const inputStyle = {
  width: '100%',
  padding: '6px 12px',
  borderRadius: 'var(--radius)',
  border: '1px solid var(--color-border)',
  background: 'var(--color-bg)',
  fontSize: 14
};

const btnStyle = {
  width: '100%',
  padding: '8px 16px',
  background: 'var(--color-cta)',
  color: '#fff',
  borderRadius: 'var(--radius)',
  border: '1px solid rgba(27,31,36,0.15)',
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer'
};

function AuthLayout({ children, title, error }: { children: React.ReactNode, title: string, error: string }) {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 64, background: 'var(--color-bg)' }}>
      <div style={{ marginBottom: 32 }}>
        <Link to="/"><Box size={48} color="var(--color-text)" /></Link>
      </div>
      <h1 style={{ fontSize: 24, fontWeight: 300, marginBottom: 24, letterSpacing: '-0.5px' }}>{title}</h1>
      
      {error && (
        <div style={{ width: 340, padding: '16px', background: '#ffebe9', color: 'var(--color-danger)', border: '1px solid rgba(255,129,130,0.4)', borderRadius: 'var(--radius)', marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      <div style={{ width: 340, padding: 24, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
        {children}
      </div>
    </div>
  );
}
