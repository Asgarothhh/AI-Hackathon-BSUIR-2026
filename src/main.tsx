import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { ModalProvider } from './contexts/ModalContext.tsx'
import { SidebarProvider } from './contexts/SidebarContext.tsx'
import { SearchProvider } from './contexts/SearchContext.tsx'
import { AnswerProvider } from './contexts/AnswerContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ModalProvider>
      <SidebarProvider>
        <SearchProvider>
          <AnswerProvider>
            <App />
          </AnswerProvider>
        </SearchProvider>
      </SidebarProvider>
    </ModalProvider>
  </StrictMode>,
)
