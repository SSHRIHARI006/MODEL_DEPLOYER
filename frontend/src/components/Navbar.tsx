import { Link, useNavigate } from 'react-router-dom';
import { useStore } from '../store';
import { Box, Search, LogOut, LayoutDashboard } from 'lucide-react';
import { useState } from 'react';

export function Navbar() {
  const { token, username, logout } = useStore();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (search.trim()) navigate(`/?search=${encodeURIComponent(search.trim())}`);
  };

  return (
    <header
      style={{
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-border)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 24,
        }}
      >
        {/* Logo */}
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
          <Box size={22} color="var(--color-text)" />
          <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--color-text)' }}>
            Model Deployer
          </span>
        </Link>

        {/* Search */}
        <form onSubmit={handleSearch} style={{ flex: 1, maxWidth: 540 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 12px',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)',
              background: 'var(--color-bg)',
            }}
          >
            <Search size={14} color="var(--color-text-muted)" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search models..."
              style={{
                border: 'none',
                outline: 'none',
                background: 'transparent',
                flex: 1,
                fontSize: 14,
                color: 'var(--color-text)',
              }}
            />
          </div>
        </form>

        {/* Right nav */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {token ? (
            <>
              <Link
                to="/dashboard"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 14,
                  color: 'var(--color-text)',
                  textDecoration: 'none',
                }}
              >
                <LayoutDashboard size={16} />
                Dashboard
              </Link>
              <Link
                to={`/@${username}`}
                style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', textDecoration: 'none' }}
              >
                @{username}
              </Link>
              <button
                onClick={() => { logout(); navigate('/'); }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 13,
                  color: 'var(--color-text-muted)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <LogOut size={14} />
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                style={{
                  fontSize: 14,
                  padding: '6px 16px',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius)',
                  color: 'var(--color-text)',
                  textDecoration: 'none',
                }}
              >
                Sign in
              </Link>
              <Link
                to="/register"
                style={{
                  fontSize: 14,
                  padding: '6px 16px',
                  background: 'var(--color-cta)',
                  color: '#fff',
                  borderRadius: 'var(--radius)',
                  border: '1px solid rgba(27,31,36,0.15)',
                  textDecoration: 'none',
                }}
              >
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
