import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthGate } from './components/AuthGate';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Problems } from './pages/Problems';
import { ProblemDetail } from './pages/ProblemDetail';
import { SheetPage } from './pages/SheetPage';
import { Analytics } from './pages/Analytics';
import { TopicsPage } from './pages/TopicsPage';
import { ActivityPage } from './pages/ActivityPage';
import { Coach } from './pages/Coach';
import { Reviews } from './pages/Reviews';
import { Missions } from './pages/Missions';
import { Collections } from './pages/Collections';
import { Contests } from './pages/Contests';
import { ICPC } from './pages/ICPC';
import { Achievements } from './pages/Achievements';
import { Settings } from './pages/Settings';

/** Keeps one broken page from blanking the whole application. */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen items-center justify-center p-6">
          <div className="card max-w-md px-5 py-5 text-center">
            <h1 className="text-base font-semibold">Something broke on this screen</h1>
            <p className="mt-1.5 text-sm text-ink-muted">
              Your data is safe — this is a display error only.
            </p>
            <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-surface-2 p-3 text-left text-[11px] text-ink-dim">
              {this.state.error.message}
            </pre>
            <button className="btn btn-primary mt-4" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <AuthGate>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="problems" element={<Problems />} />
            <Route path="problems/:id" element={<ProblemDetail />} />
            <Route path="sheets/:slug" element={<SheetPage />} />
            <Route path="missions" element={<Missions />} />
            <Route path="recommendations" element={<Missions />} />
            <Route path="reviews" element={<Reviews />} />
            <Route path="collections" element={<Collections />} />
            <Route path="collections/:slug" element={<Collections />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="analytics/topics" element={<TopicsPage />} />
            <Route path="analytics/activity" element={<ActivityPage />} />
            <Route path="contests" element={<Contests />} />
            <Route path="icpc" element={<ICPC />} />
            <Route path="achievements" element={<Achievements />} />
            <Route path="coach" element={<Coach />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthGate>
    </ErrorBoundary>
  );
}
