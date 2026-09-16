import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app/App'
import './styles/global.css'
import './styles/home.css'
import './styles/workspace.css'

createRoot(document.getElementById('root')!).render(<BrowserRouter><App /></BrowserRouter>)
