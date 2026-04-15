import { useState, useEffect } from 'react'

function App() {
  // This state variable hold the data we get from the backend
  const [devices, setDevices] = useState([])

  //useEffect runs automatically when the page loads
  useEffect(() =>{
    // 1. Ask the python backend for the device list
    fetch('http://127.0.0.1:8000/device/')
      .then(response => response.json())
      .then(data => {
        // 2. Save that data into our React state
        setDevices(data)
      })
      .catch(error => console.error("Error fetching data:", error))
  }, [])

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', backgroundColor: '#1e1e1e', color: '#fff', minHeight: '100vh'}}>
      <h1>NetGen Pro Dashboard</h1>
      <h2>Connected Devices:</h2>

      {/* This prints our raw database information directly to the screen */}
      <pre style={{ backgroundColor: '#2d2d2d', padding: '1rem', borderRadius: '8px'}}>
        {JSON.stringify(devices, null, 2)}
      </pre>
    </div>
  )
}

export default App