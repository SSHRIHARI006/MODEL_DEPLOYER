import { Link } from 'react-router-dom';
import { Box, Lock, Globe } from 'lucide-react';

export interface ModelData {
  id: string;
  name: string;
  framework: string;
  task_type: string;
  description: string;
  cost_per_run: string;
  is_public: boolean;
  owner_username: string;
  total_versions: number;
  created_at: string;
}

interface ModelCardProps {
  model: ModelData;
}

export function ModelCard({ model }: ModelCardProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        padding: 16,
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)',
        height: '100%',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Box size={16} color="var(--color-text-muted)" />
          <Link
            to={`/@${model.owner_username}/${model.name}`}
            style={{
              fontWeight: 600,
              fontSize: 16,
              color: 'var(--color-accent)',
              fontFamily: 'var(--font-mono)',
              wordBreak: 'break-word',
            }}
          >
            {model.owner_username} / {model.name}
          </Link>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '2px 8px',
            border: '1px solid var(--color-border)',
            borderRadius: 12,
            fontSize: 12,
            color: 'var(--color-text-muted)',
            background: 'var(--color-bg)',
          }}
        >
          {model.is_public ? <Globe size={12} /> : <Lock size={12} />}
          {model.is_public ? 'Public' : 'Private'}
        </div>
      </div>

      <p style={{ fontSize: 14, color: 'var(--color-text-muted)', flex: 1, marginBottom: 16 }}>
        {model.description || 'No description provided.'}
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 12, color: 'var(--color-text-muted)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: model.framework.toLowerCase() === 'pytorch' ? '#ee4c2c' : '#f9a826',
            }}
          />
          {model.framework}
        </div>
        <div>{model.task_type}</div>
        <div>•</div>
        <div style={{ fontWeight: 600 }}>{parseFloat(model.cost_per_run).toFixed(4)} credits/run</div>
      </div>
    </div>
  );
}
