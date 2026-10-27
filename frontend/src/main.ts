import { createApp } from 'vue'
import { useColorScheme } from 'frappe-ui'
import App from './App.vue'
import { router } from './router.ts'
import './style.css'

const { setColorScheme } = useColorScheme()

// Light is the default. A person's own choice (saved by the toggle) always wins.
try {
  const saved = localStorage.getItem('theme')
  if (!saved || saved === 'system') setColorScheme('light')
} catch {
  setColorScheme('light')
}

createApp(App).use(router).mount('#app')
