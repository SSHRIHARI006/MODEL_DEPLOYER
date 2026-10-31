import { ArrowRight, Box, Check, Code2, KeyRound, Layers3, MonitorCheck, Package, Server, ShieldCheck, Workflow } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { useStore } from '../store';

const features = [
  { icon: Package, title: 'Model hosting', text: 'Upload trained model bundles and manage their artifacts from one control plane.' },
  { icon: Layers3, title: 'Model versioning', text: 'Keep distinct versions and associate every deployment with an immutable model version.' },
  { icon: Code2, title: 'API inference', text: 'Serve deployed models through predictable HTTP prediction endpoints.' },
  { icon: Server, title: 'Framework support', text: 'Use the implemented CPU inference paths for scikit-learn and PyTorch models.' },
  { icon: KeyRound, title: 'API keys', text: 'Create model-specific or universal credentials for authenticated inference.' },
  { icon: MonitorCheck, title: 'Usage visibility', text: 'Inspect deployment state, prediction activity and available monitoring information.' },
];

const steps = [
  ['01', 'Upload your model', 'Bring a validated ZIP bundle with its manifest, dependencies and artifact.'],
  ['02', 'Configure and deploy', 'Choose a model version and follow its asynchronous build status.'],
  ['03', 'Create an API key', 'Issue a model-scoped key for the clients that should call it.'],
  ['04', 'Send predictions', 'Call the HTTP endpoint with your JWT, API key and model inputs.'],
];

export function Landing() {
  const token = useStore((state) => state.token);
  return (
    <div className="landing-shell">
      <Navbar publicNav />
      <main>
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <span className="eyebrow"><Box size={14} /> Developer-focused model infrastructure</span>
            <h1>Deploy machine learning models as APIs.</h1>
            <p>Upload, version, deploy and serve your machine learning models through simple, manageable prediction APIs.</p>
            <div className="hero-actions">
              <a className="button button-primary" href="/docs#demo-model">Try the demo <ArrowRight size={16} /></a>
              <Link className="button button-secondary" to="/docs">Explore documentation</Link>
            </div>
            <div className="hero-proof"><Check size={16} /> Authenticated APIs</div><div className="hero-proof"><Check size={16} /> Immutable model versions</div>
          </div>
          <div className="hero-preview">
            <div className="preview-bar"><span /><span /><span /><strong>ModelDeploy / Explore</strong></div>
            <img src="/screenshots/model-explorer.png" alt="ModelDeploy model explorer showing framework filters and model cards" />
          </div>
        </section>

        <section className="landing-section showcase-section" aria-labelledby="showcase-title">
          <div className="section-heading"><span className="eyebrow">The product, in view</span><h2 id="showcase-title">A clear path from model bundle to endpoint.</h2><p>Explore the real ModelDeploy interface and documentation before you sign in.</p></div>
          <div className="showcase-grid">
            <figure className="showcase-card showcase-wide"><img src="/screenshots/model-explorer.png" alt="Actual ModelDeploy public model explorer" /><figcaption><strong>Explore the model directory</strong><span>Search and filter the models available to your users.</span></figcaption></figure>
            <figure className="showcase-card"><img src="/screenshots/documentation.png" alt="Actual ModelDeploy documentation page" /><figcaption><strong>Follow the API contract</strong><span>Use the built-in docs to move from registration to prediction.</span></figcaption></figure>
          </div>
        </section>

        <section className="landing-section" id="features" aria-labelledby="features-title">
          <div className="section-heading"><span className="eyebrow">Built for the workflow</span><h2 id="features-title">The essentials for serving models.</h2><p>Focused platform primitives for teams that want a manageable route from artifact to inference.</p></div>
          <div className="feature-grid">{features.map(({ icon: Icon, title, text }) => <article className="feature-card" key={title}><Icon size={20} /><h3>{title}</h3><p>{text}</p></article>)}</div>
        </section>

        <section className="landing-section workflow-section" aria-labelledby="workflow-title">
          <div className="section-heading"><span className="eyebrow"><Workflow size={14} /> How it works</span><h2 id="workflow-title">Four steps to your first prediction.</h2></div>
          <div className="steps-grid">{steps.map(([number, title, text]) => <article className="step-card" key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div>
        </section>

        <section className="landing-cta" id="demo-cta"><div><span className="eyebrow"><ShieldCheck size={14} /> Curated first deployment</span><h2>Your first model deployment starts here.</h2><p>Try ModelDeploy with a ready-to-upload sample model, then make a real prediction through the documented API.</p></div><a className="button button-primary" href="/docs#demo-model">Try the demo model <ArrowRight size={16} /></a></section>
      </main>
      <footer className="landing-footer"><div><strong>ModelDeploy</strong><span>Manage the route from model artifact to prediction API.</span></div><nav><Link to="/docs">Documentation</Link><a href="https://github.com/SSHRIHARI006/MODEL_DEPLOYER" target="_blank" rel="noreferrer">GitHub</a>{token ? <Link to="/dashboard">Dashboard</Link> : <><Link to="/login">Sign in</Link><Link to="/register">Get started</Link></>}</nav></footer>
    </div>
  );
}
