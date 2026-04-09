import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { BrowserRouter } from 'react-router-dom'
import { Provider } from 'react-redux'
import { store, persistor } from './redux/store.js'
import { PersistGate } from 'redux-persist/integration/react'

const LoadingScreen = () => (
  <div className='min-h-screen w-full flex items-center justify-center bg-[#0b0b0a] text-white'>
    <div className='text-center'>
      <div className='mb-4 text-2xl font-bold text-[#ff2e43]'>SteamyPot</div>
      <div className='animate-spin rounded-full h-12 w-12 border-b-2 border-[#ff2e43] mx-auto'></div>
      <p className='mt-4 text-gray-400'>Loading your session...</p>
    </div>
  </div>
)

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <Provider store={store}>
      <PersistGate loading={<LoadingScreen />} persistor={persistor}>
        <App />
      </PersistGate>
    </Provider>
  </BrowserRouter>
)
