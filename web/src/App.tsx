import { useState, useEffect } from 'react'
import './App.css'

interface HealthStatus {
  api: boolean | null
  worker: boolean | null
}

function App() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>({
    api: null,
    worker: null
  })

  const checkHealth = async () => {
    try {
      const apiResponse = await fetch('http://localhost:8080/health')
      const apiOk = apiResponse.ok
      setHealthStatus(prev => ({ ...prev, api: apiOk }))
    } catch (error) {
      setHealthStatus(prev => ({ ...prev, api: false }))
    }

    try {
      const workerResponse = await fetch('http://localhost:8090/health')
      const workerOk = workerResponse.ok
      setHealthStatus(prev => ({ ...prev, worker: workerOk }))
    } catch (error) {
      setHealthStatus(prev => ({ ...prev, worker: false }))
    }
  }

  useEffect(() => {
    checkHealth()
    const interval = setInterval(checkHealth, 5000) // Check every 5 seconds
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="App">
      <header className="App-header">
        <h1>jsonify2ai Memory System</h1>
        <div className="health-status">
          <h2>Service Health</h2>
          <div className="service-status">
            <div className={`status ${healthStatus.api === null ? 'loading' : healthStatus.api ? 'healthy' : 'unhealthy'}`}>
              API Service: {healthStatus.api === null ? 'Checking...' : healthStatus.api ? 'Healthy' : 'Unhealthy'}
            </div>
            <div className={`status ${healthStatus.worker === null ? 'loading' : healthStatus.worker ? 'healthy' : 'unhealthy'}`}>
              Worker Service: {healthStatus.worker === null ? 'Checking...' : healthStatus.worker ? 'Healthy' : 'Unhealthy'}
            </div>
          </div>
          <button onClick={checkHealth} className="refresh-btn">
            Refresh Health Check
          </button>
        </div>
      </header>
    </div>
  )
}

export default App
