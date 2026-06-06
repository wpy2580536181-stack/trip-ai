import { createApp } from 'vue'
import router from './router'
import Vant from 'vant'
import 'vant/lib/index.css'
import './style.css'
import './styles/common.css'
import App from './App.vue'

const app = createApp(App)
app.use(Vant)
app.use(router)
app.mount('#app')
