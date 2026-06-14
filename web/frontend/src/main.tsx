import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { PlatformUpdatesProvider } from './hooks/usePlatformUpdates'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <PlatformUpdatesProvider>
          <App />
        </PlatformUpdatesProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>
)
