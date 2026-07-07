import { useEffect, useState } from 'react';
import { useParams, Navigate, Link } from 'react-router-dom';
import { api } from '../api';
import { Navbar } from '../components/Navbar';
import { type ModelData } from '../components/ModelCard';
import { Book, Calendar } from 'lucide-react';

interface UserProfileData {
  username: string;
  email: string;
  bio: string;
  avatar_url: string;
  joined: string;
  total_public_models: number;
  models: ModelData[];
}

export function UserProfile() {
  const { namespace } = useParams();
  
  if (!namespace?.startsWith('@')) {
    return <Navigate to="/404" replace />;
  }
  
  const username = namespace.substring(1);
  const [profile, setProfile] = useState<UserProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.get<UserProfileData>(`/users/@${username}/`)
      .then(res => {
        setProfile(res);
        setError(null);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [username]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      
      <main style={{ flex: 1, maxWidth: 1280, margin: '0 auto', width: '100%', padding: '32px 24px', display: 'flex', gap: 32 }}>
        
        {loading && <div style={{ color: 'var(--color-text-muted)' }}>Loading profile...</div>}
        {error && <div style={{ color: 'var(--color-danger)' }}>{error}</div>}
        
        {profile && (
          <>
            {/* Left Sidebar */}
            <aside style={{ width: 296, flexShrink: 0 }}>
              <div style={{ marginBottom: 16 }}>
                <img 
                  src={profile.avatar_url || `https://api.dicebear.com/7.x/identicon/svg?seed=${profile.username}`}
                  alt={profile.username}
                  style={{ width: 296, height: 296, borderRadius: '50%', border: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}
                />
              </div>
              <h1 style={{ fontSize: 24, fontWeight: 600, lineHeight: 1.25, marginBottom: 16 }}>
                {profile.username}
              </h1>
              {profile.bio && (
                <div style={{ fontSize: 16, marginBottom: 16 }}>
                  {profile.bio}
                </div>
              )}
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14, color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)', paddingTop: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Calendar size={16} />
                  Joined {new Date(profile.joined).getFullYear()}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Book size={16} />
                  {profile.total_public_models} Public Models
                </div>
              </div>
            </aside>

            {/* Main Content */}
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', borderBottom: '1px solid var(--color-border)', marginBottom: 24 }}>
                <div style={{ padding: '8px 16px', borderBottom: '2px solid var(--color-accent)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Book size={16} color="var(--color-text-muted)" />
                  Repositories
                  <span style={{ background: 'var(--color-border)', borderRadius: '12px', padding: '2px 8px', fontSize: 12, fontWeight: 500 }}>
                    {profile.total_public_models}
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {profile.models.length === 0 ? (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--color-text-muted)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: 'var(--color-surface)' }}>
                    {profile.username} doesn't have any public models yet.
                  </div>
                ) : (
                  profile.models.map(model => (
                    <div key={model.id} style={{ padding: '24px 0', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                          <Link to={`/@${profile.username}/${model.name}`} style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'none' }}>
                            {model.name}
                          </Link>
                          <span style={{ fontSize: 12, padding: '2px 8px', border: '1px solid var(--color-border)', borderRadius: '2em', color: 'var(--color-text-muted)' }}>
                            Public
                          </span>
                        </div>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: 14, marginBottom: 12 }}>
                          {model.description || 'No description provided.'}
                        </p>
                        <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--color-text-muted)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: model.framework.toLowerCase() === 'pytorch' ? '#ee4c2c' : '#f9a826' }} />
                            {model.framework}
                          </div>
                          <div>{model.task_type}</div>
                          <div>Updated on {new Date(model.created_at).toLocaleDateString()}</div>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--color-text-muted)' }}>
                        <div style={{ fontWeight: 600, color: 'var(--color-text)' }}>{parseFloat(model.cost_per_run).toFixed(4)}</div>
                        <div>credits / run</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
