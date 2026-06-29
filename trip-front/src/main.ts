import { createApp } from 'vue'
import router from './router'
import './style.css'
import './styles/common.css'
import App from './App.vue'
import { checkAndCleanExpiredToken } from './utils/auth'

checkAndCleanExpiredToken()

const app = createApp(App)
app.use(router)
app.mount('#app')
