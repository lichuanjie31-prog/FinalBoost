import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app/App'
import './styles/global.css'
import './styles/home.css'
import './styles/workspace.css'
import './styles/aipanel.css'
import './styles/study.css'
import './styles/question-bank.css'
import './styles/training.css'

createRoot(document.getElementById('root')!).render(<BrowserRouter><App /></BrowserRouter>)
