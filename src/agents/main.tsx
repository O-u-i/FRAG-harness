import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import AgentReviewApp from './AgentReviewApp';

createRoot(document.getElementById('root')!).render(
  <StrictMode><AgentReviewApp /></StrictMode>,
);
