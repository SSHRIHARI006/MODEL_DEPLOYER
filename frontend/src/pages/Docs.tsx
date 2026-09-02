import type { ReactNode } from 'react';
import { Navbar } from '../components/Navbar';

const sections = [
  { id: 'getting-started', label: 'Getting started' },
  { id: 'model-package', label: 'Model package format' },
  { id: 'uploading', label: 'Uploading a model' },
  { id: 'deploying', label: 'Deploying' },
  { id: 'inference', label: 'Running inference' },
  { id: 'authentication', label: 'Authentication for inference' },
  { id: 'self-hosting', label: 'Self-hosting' },
];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} style={{ marginBottom: 40, scrollMarginTop: 96 }}>
      <h2
        style={{
          fontSize: 22,
          fontWeight: 700,
          marginBottom: 16,
          paddingBottom: 8,
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre
      style={{
        padding: 12,
        background: 'var(--color-terminal)',
        color: 'var(--color-terminal-text)',
        borderRadius: 'var(--radius)',
        fontSize: 12,
        overflow: 'auto',
        margin: '12px 0',
        lineHeight: 1.6,
      }}
    >
      {children}
    </pre>
  );
}

function FieldTable({ rows }: { rows: [string, string][] }) {
  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: 13,
        margin: '12px 0',
      }}
    >
      <thead>
        <tr>
          {['Field', 'Description'].map((heading) => (
            <th
              key={heading}
              style={{
                textAlign: 'left',
                padding: '8px 12px',
                background: 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                fontWeight: 600,
              }}
            >
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(([field, description]) => (
          <tr key={field}>
            <td
              className="font-mono"
              style={{ padding: '8px 12px', border: '1px solid var(--color-border)', whiteSpace: 'nowrap' }}
            >
              {field}
            </td>
            <td style={{ padding: '8px 12px', border: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}>
              {description}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Docs() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />

      <main style={{ flex: 1, maxWidth: 1280, margin: '0 auto', width: '100%', padding: '40px 24px' }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: 32, fontWeight: 800, letterSpacing: '-0.03em', marginBottom: 8 }}>
            Documentation
          </h1>
          <p style={{ fontSize: 16, color: 'var(--color-text-muted)' }}>
            Everything you need to go from an empty account to a live prediction endpoint.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 32, alignItems: 'flex-start' }}>
          <aside style={{ width: 240, flexShrink: 0, position: 'sticky', top: 96 }}>
            <div
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
                background: 'var(--color-surface)',
                padding: 16,
              }}
            >
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--color-text-muted)',
                  textTransform: 'uppercase',
                  marginBottom: 8,
                }}
              >
                On this page
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {sections.map((section) => (
                  <a
                    key={section.id}
                    href={`#${section.id}`}
                    style={{ fontSize: 14, color: 'var(--color-accent)', textDecoration: 'none' }}
                  >
                    {section.label}
                  </a>
                ))}
              </div>
            </div>
          </aside>

          <div style={{ flex: 1, minWidth: 0 }}>
            <Section id="getting-started" title="Getting started">
              <p style={{ marginBottom: 8 }}>
                All API endpoints live under <code>/api/</code> and use JSON. Create an account, then exchange
                credentials for a JWT access token.
              </p>
              <CodeBlock>{`# Register
curl -X POST http://localhost:8000/api/auth/register/ \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com", "username": "you", "password": "STRONG_PASSWORD"}'
# 201 Created

# Login — returns access and refresh tokens
curl -X POST http://localhost:8000/api/auth/login/ \\
  -H "Content-Type: application/json" \\
  -d '{"email": "you@example.com", "password": "STRONG_PASSWORD"}'
# {"access": "...", "refresh": "..."}

# Refresh an expired access token
curl -X POST http://localhost:8000/api/auth/refresh/ \\
  -H "Content-Type: application/json" \\
  -d '{"refresh": "REFRESH_TOKEN"}'`}</CodeBlock>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
                Send the access token as <code>Authorization: Bearer &lt;access&gt;</code> on every authenticated
                request.
              </p>
            </Section>

            <Section id="model-package" title="Model package format">
              <p style={{ marginBottom: 8 }}>
                A model is uploaded as a single <code>.zip</code> archive — this is enforced server-side, no other
                extension is accepted. The archive must contain, at its root:
              </p>
              <CodeBlock>{`model.zip
├── model.yaml          # manifest (required)
├── requirements.txt    # dependencies for the model environment
└── model.pkl           # trained artifact (name taken from model.yaml)`}</CodeBlock>
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '16px 0 8px' }}>Common manifest fields</h3>
              <FieldTable
                rows={[
                  ['name', 'Model name, unique per owner.'],
                  ['framework', 'sklearn or pytorch.'],
                  ['python_version', 'Python version for the model environment, e.g. "3.12".'],
                  ['requirements', 'Path to the requirements file inside the zip.'],
                  ['model_artifact', 'Path to the trained artifact inside the zip.'],
                  ['task_type', 'regression, classification, or binary_classification.'],
                ]}
              />
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '16px 0 8px' }}>sklearn models</h3>
              <p style={{ marginBottom: 8 }}>
                The artifact is a pickled estimator (<code>model.pkl</code>) loaded with joblib. Inference receives
                your <code>instances</code> as a pandas DataFrame and calls <code>model.predict(...)</code>.
              </p>
              <CodeBlock>{`name: my_regressor
framework: sklearn
python_version: "3.12"
requirements: requirements.txt
model_artifact: model.pkl
task_type: regression`}</CodeBlock>
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '16px 0 8px' }}>PyTorch models</h3>
              <FieldTable
                rows={[
                  ['device', 'Inference device, e.g. cpu.'],
                  ['load_method', 'state_dict — the artifact is a saved state dict.'],
                  ['model_class_file', 'Python file in the zip defining the model class.'],
                  ['model_class_name', 'Class name to instantiate from that file.'],
                  ['input_type', 'tabular, sequence, or image_1d.'],
                ]}
              />
              <CodeBlock>{`name: my_classifier
framework: pytorch
python_version: '3.12'
requirements: requirements.txt
model_artifact: model.pt
task_type: classification
device: cpu
load_method: state_dict
model_class_file: model_architecture.py
model_class_name: MyClassifier
input_type: tabular`}</CodeBlock>
            </Section>

            <Section id="uploading" title="Uploading a model">
              <CodeBlock>{`curl -X POST http://localhost:8000/api/models/upload/ \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -F file=@model.zip
# 201 Created
# {"model_id": "...", "model_version_id": "...", "version": "v1"}`}</CodeBlock>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
                Keep <code>model_version_id</code> — it is the only input the deployment endpoint needs.
              </p>
            </Section>

            <Section id="deploying" title="Deploying">
              <CodeBlock>{`curl -X POST http://localhost:8000/api/deployments/ \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"model_version_id": "MODEL_VERSION_ID"}'
# 202 Accepted — build runs asynchronously`}</CodeBlock>
              <p style={{ marginBottom: 8 }}>
                The build is queued as a durable Celery task, so it survives an API restart. Poll the deployment
                until it reaches a terminal state:
              </p>
              <CodeBlock>{`curl http://localhost:8000/api/deployments/DEPLOYMENT_ID/ \\
  -H "Authorization: Bearer ACCESS_TOKEN"`}</CodeBlock>
              <FieldTable
                rows={[
                  ['PENDING', 'Queued for build.'],
                  ['BUILDING', 'Environment install / healthcheck in progress.'],
                  ['RUNNING', 'Ready to serve predictions.'],
                  ['FAILED', 'Terminal failure — see last_error.'],
                  ['STOPPED', 'Terminal — stopped by request.'],
                ]}
              />
            </Section>

            <Section id="inference" title="Running inference">
              <CodeBlock>{`curl -X POST http://localhost:8000/api/predict/MODEL_ID/ \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "X-API-Key: MODEL_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"instances": [{"f1": 0.5, "f2": -0.3, "f3": 1.2, "f4": 0.7}]}'
# {"predictions": [...], "probabilities": [...], "metadata": {...}}`}</CodeBlock>
              <FieldTable
                rows={[
                  ['Tabular models', 'instances is a list of feature dicts: [{"f1": 0.5, ...}].'],
                  ['Sequence / image_1d models', 'instances is a list of numeric lists: [[0.5, -0.3, 1.2, 0.7]].'],
                ]}
              />
              <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
                Predictions are cached in Redis. Repeating an identical request against the same model version
                within the cache TTL is served from cache instead of re-running the model. Deploying a new model
                version never serves results cached for an older version. Upstream failures map to 502/503/504.
              </p>
            </Section>

            <Section id="authentication" title="Authentication for inference">
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 8px' }}>Per-model API keys</h3>
              <p style={{ marginBottom: 8 }}>
                Create a key for a model you own, then send it as <code>X-API-Key</code> alongside your JWT when
                calling <code>/api/predict/&lt;model_id&gt;/</code>.
              </p>
              <CodeBlock>{`curl -X POST http://localhost:8000/api/keys/ \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"model_id": "MODEL_ID", "name": "my-key"}'
# 201 Created — the key value is shown only once`}</CodeBlock>
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '16px 0 8px' }}>Universal keys</h3>
              <p style={{ marginBottom: 8 }}>
                Universal keys are user-level and work with the namespaced inference endpoint. They start with{' '}
                <code>md_live_</code> and are passed as the bearer token.
              </p>
              <CodeBlock>{`curl -X POST http://localhost:8000/api/keys/universal/ \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "my-universal-key"}'

curl -X POST http://localhost:8000/api/v1/inference/@USERNAME/MODEL_NAME/ \\
  -H "Authorization: Bearer md_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"instances": [{"f1": 0.5, "f2": -0.3, "f3": 1.2, "f4": 0.7}]}'`}</CodeBlock>
            </Section>

            <Section id="self-hosting" title="Self-hosting">
              <p style={{ marginBottom: 8 }}>
                The full self-hosting runbook lives in <code>SELF_HOSTING.md</code> at the repository root. In short:
              </p>
              <CodeBlock>{`cp .env.example .env    # then replace every placeholder value
docker compose up --build -d
docker compose exec api python manage.py createsuperuser`}</CodeBlock>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 14 }}>
                Compose starts PostgreSQL, Redis, MinIO, the Django API, the Celery worker, the FastAPI runner, and
                the frontend with named volumes for durable storage. It is single-node and does not terminate TLS —
                put a reverse proxy in front of it.
              </p>
            </Section>
          </div>
        </div>
      </main>
    </div>
  );
}
