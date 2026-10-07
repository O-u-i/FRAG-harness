import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
const App = lazy(() => import('./App'));
const AgentReviewApp = lazy(() => import('./agents/AgentReviewApp'));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p>Loading FRAG…</p>}>
      {window.location.pathname === '/review' ? <AgentReviewApp /> : <App />}
    </Suspense>
  </StrictMode>,
);
