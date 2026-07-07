import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Explore } from './pages/Explore';
import { UserProfile } from './pages/UserProfile';
import { ModelRepo } from './pages/ModelRepo';
import { Dashboard } from './pages/Dashboard';
import { Login, Register } from './pages/Auth';
import { Navbar } from './components/Navbar';

function NotFound() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
        <h1 style={{ fontSize: 48, fontWeight: 800, marginBottom: 16 }}>404</h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 18 }}>The page you are looking for could not be found.</p>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Directory */}
        <Route path="/" element={<Explore />} />
        
        {/* Auth */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        
        {/* Private Dashboard */}
        <Route path="/dashboard/*" element={<Dashboard />} />
        
        {/* Dynamic Namespaces */}
        <Route path="/:namespace" element={<UserProfile />} />
        <Route path="/:namespace/:model_name" element={<ModelRepo />} />
        
        {/* 404 Catch-all */}
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
