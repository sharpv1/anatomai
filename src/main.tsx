import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import BackendApp from './backend/BackendApp';
import {backendConfig} from './backend/config';
import './styles/viewport.css';

createRoot(document.getElementById('root')!).render(<StrictMode>{backendConfig.enabled?<BackendApp/>:<App />}</StrictMode>);
