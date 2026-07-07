import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { ModelCard, type ModelData } from '../components/ModelCard';
import { Navbar } from '../components/Navbar';
import { Search } from 'lucide-react';

interface PaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: ModelData[];
}

export function Explore() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const querySearch = searchParams.get('search') || '';
  const queryFramework = searchParams.get('framework') || '';

  const [searchInput, setSearchInput] = useState(querySearch);

  useEffect(() => {
    let url = '/models/explore/?page_size=20';
    if (querySearch) url += `&search=${encodeURIComponent(querySearch)}`;
    if (queryFramework) url += `&framework=${encodeURIComponent(queryFramework)}`;

    setLoading(true);
    api.get<PaginatedResponse>(url)
      .then(res => {
        setData(res);
        setError(null);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [querySearch, queryFramework]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newParams = new URLSearchParams(searchParams);
    if (searchInput) newParams.set('search', searchInput);
    else newParams.delete('search');
    setSearchParams(newParams);
  };

  const handleFrameworkFilter = (framework: string) => {
    const newParams = new URLSearchParams(searchParams);
    if (framework) newParams.set('framework', framework);
    else newParams.delete('framework');
    setSearchParams(newParams);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      
      <main style={{ flex: 1, maxWidth: 1280, margin: '0 auto', width: '100%', padding: '40px 24px' }}>
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <h1 style={{ fontSize: 40, fontWeight: 800, marginBottom: 16, letterSpacing: '-0.04em' }}>
            The Public Compute Marketplace
          </h1>
          <p style={{ fontSize: 20, color: 'var(--color-text-muted)', maxWidth: 600, margin: '0 auto' }}>
            Discover, host, and run machine learning models with a single Universal API key.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 32, alignItems: 'flex-start' }}>
          {/* Sidebar Filters */}
          <aside style={{ width: 250, flexShrink: 0 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--color-border)' }}>
              Filters
            </h3>
            
            <form onSubmit={handleSearchSubmit} style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', padding: '6px 12px', background: 'var(--color-surface)' }}>
                <Search size={14} color="var(--color-text-muted)" style={{ marginRight: 8 }} />
                <input 
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  placeholder="Find a model..."
                  style={{ border: 'none', outline: 'none', background: 'transparent', width: '100%', fontSize: 14 }}
                />
              </div>
            </form>

            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8, textTransform: 'uppercase' }}>Framework</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[
                  { id: '', label: 'All Frameworks' },
                  { id: 'pytorch', label: 'PyTorch' },
                  { id: 'sklearn', label: 'Scikit-Learn' }
                ].map(fw => (
                  <button
                    key={fw.id}
                    onClick={() => handleFrameworkFilter(fw.id)}
                    style={{
                      textAlign: 'left',
                      padding: '6px 12px',
                      borderRadius: 'var(--radius)',
                      border: 'none',
                      background: queryFramework === fw.id ? 'var(--color-accent)' : 'transparent',
                      color: queryFramework === fw.id ? '#fff' : 'var(--color-text)',
                      fontSize: 14,
                      cursor: 'pointer'
                    }}
                  >
                    {fw.label}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* Main Grid */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ fontSize: 20, fontWeight: 600 }}>
                {querySearch ? `Results for "${querySearch}"` : 'Trending Models'}
              </h2>
              <div style={{ fontSize: 14, color: 'var(--color-text-muted)' }}>
                {data ? `${data.count} models found` : '...'}
              </div>
            </div>

            {error && <div style={{ padding: 16, background: '#ffebe9', color: 'var(--color-danger)', border: '1px solid rgba(255,129,130,0.4)', borderRadius: 'var(--radius)', marginBottom: 24 }}>{error}</div>}

            {loading ? (
              <div style={{ textAlign: 'center', padding: 48, color: 'var(--color-text-muted)' }}>Loading models...</div>
            ) : data?.results.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 48, color: 'var(--color-text-muted)', background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
                No models found matching your criteria.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                {data?.results.map(model => (
                  <ModelCard key={model.id} model={model} />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
