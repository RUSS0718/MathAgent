import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/main.css'
import 'katex/dist/katex.min.css'
createApp(App).use(createPinia()).mount('#app')
