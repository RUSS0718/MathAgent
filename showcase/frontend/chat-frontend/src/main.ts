import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/main.css'
import 'katex/dist/katex.min.css'
try { document.documentElement.dataset.theme = localStorage.getItem('mathagent-theme') === 'dark' ? 'dark' : 'light' } catch { /* Theme persistence is optional. */ }
createApp(App).use(createPinia()).mount('#app')
import './styles/review.css'
