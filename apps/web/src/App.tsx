import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Layout from './components/Layout'
import UploadPage from './pages/UploadPage'
import ProgressPage from './pages/ProgressPage'
import ResultPage from './pages/ResultPage'

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <AnimatePresence mode="wait">
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/jobs/:jobId" element={<ProgressPage />} />
            <Route path="/jobs/:jobId/result" element={<ResultPage />} />
          </Routes>
        </AnimatePresence>
      </Layout>
    </BrowserRouter>
  )
}

export default App
