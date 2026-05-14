import { useState, useRef, useEffect } from 'react';

export default function Configuration({ selectedSwitches, selectedRouters }) {
  const [aiPrompt, setAiPrompt] = useState('');
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [generatedAiConfig, setGeneratedAiConfig] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // --- SIMULATION STATES ---
  const [isSimulating, setIsSimulating] = useState(false);
  const [simulationLogs, setSimulationLogs] = useState([]);
  const terminalEndRef = useRef(null); // Used to auto-scroll the terminal

  // Auto-scroll the terminal to the bottom whenever new logs arrive
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [simulationLogs]);

  const handleGenerateConfig = () => {
    if (!aiPrompt) return alert("Please enter a prompt first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) {
      if(!window.confirm("No target devices selected. Generate general configuration anyway?")) return;
    }

    setIsAiGenerating(true);
    fetch('http://127.0.0.1:8000/configuration/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: aiPrompt,
        switches: selectedSwitches,
        routers: selectedRouters
      })
    })
    .then(async res => {
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      return res.json();
    })
    .then(data => {
      setGeneratedAiConfig(data.config);
      setIsAiGenerating(false);
      setIsEditing(false);
    })
    .catch(err => { 
      console.error(err); 
      alert(`Generation Failed: ${err.message}`); 
      setIsAiGenerating(false); 
    });
  };

// --- STREAMING SIMULATION ENGINE ---
  const handleSimulate = async () => {
    if (!generatedAiConfig) return alert("Please generate a configuration first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) return alert("Please select target devices from the sidebar.");

    setIsSimulating(true);
    setSimulationLogs([]); // Clear old logs

    try {
      const response = await fetch('http://127.0.0.1:8000/configuration/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_text: generatedAiConfig,
          switches: selectedSwitches,
          routers: selectedRouters
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Simulation failed to start.");
      }

      // Read the stream chunk by chunk
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = ""; // NEW: Buffer to hold incomplete network chunks

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Add the new chunk to whatever was left over in the buffer
        buffer += decoder.decode(value, { stream: true });
        
        // Split by our double-newline delimiter
        const parts = buffer.split('\n\n');
        
        // The last part might be an incomplete network chunk, so pop it off and leave it in the buffer for next time!
        buffer = parts.pop(); 

        for (let part of parts) {
          if (part.startsWith('data: ')) {
            const cleanText = part.substring(6); // Safely remove 'data: '
            setSimulationLogs(prev => [...prev, cleanText]);
          }
        }
      }
    } catch (err) {
      console.error(err);
      setSimulationLogs(prev => [...prev, `\n[ERROR]: ${err.message}`]);
    } finally {
      setIsSimulating(false);
    }
  };

  // Helper function to colorize comments
  const formatConfigText = (text) => {
    if (!text) return null;
    return text.split('\n').map((line, index) => {
      if (line.trim().startsWith('!')) {
        return <span key={index} style={{ color: '#569cd6' }}>{line}<br/></span>;
      }
      return <span key={index}>{line}<br/></span>;
    });
  };

  const getPlaceholderText = () => {
    if (selectedSwitches.length > 0 || selectedRouters.length > 0) {
      return `! Ready to generate config for:\n! Switches: ${selectedSwitches.join(', ') || 'None'}\n! Routers: ${selectedRouters.join(', ') || 'None'}`;
    }
    return `! Please select target devices from the sidebar and enter a prompt...`;
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <h2>AI Configuration Engine</h2>
      
      {/* 1. PROMPT BOX */}
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
        <textarea 
          placeholder="e.g., 'Configure VLAN 10 named GUEST and VLAN 20 named IOT...'" 
          value={aiPrompt} 
          onChange={(e) => setAiPrompt(e.target.value)} 
          style={{ width: '100%', height: '100px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', padding: '15px', borderRadius: '4px', resize: 'vertical' }} 
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
          <button 
            onClick={handleGenerateConfig} 
            disabled={isAiGenerating} 
            style={{ padding: '10px 20px', backgroundColor: isAiGenerating ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: isAiGenerating ? 'wait' : 'pointer', fontWeight: 'bold' }}
          >
            {isAiGenerating ? 'Generating...' : 'Generate Logic'}
          </button>
        </div>
      </div>
      
      {/* 2. CONFIGURATION BOX */}
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ margin: 0 }}>Generated Configuration</h3>
          
          <button 
            onClick={() => setIsEditing(!isEditing)}
            disabled={!generatedAiConfig && !isEditing}
            style={{ padding: '6px 15px', backgroundColor: isEditing ? '#4caf50' : '#e6a23c', color: isEditing ? 'white' : 'black', border: 'none', borderRadius: '4px', cursor: (!generatedAiConfig && !isEditing) ? 'not-allowed' : 'pointer', fontWeight: 'bold', fontSize: '0.9rem' }}
          >
            {isEditing ? '💾 Save Changes' : '✏️ Edit Config'}
          </button>
        </div>

        {isEditing ? (
          <textarea 
            value={generatedAiConfig}
            onChange={(e) => setGeneratedAiConfig(e.target.value)}
            style={{ width: '100%', minHeight: '200px', backgroundColor: '#1e1e1e', color: '#d4d4d4', border: '1px solid #007acc', padding: '15px', borderRadius: '4px', resize: 'vertical', fontFamily: 'monospace', outline: 'none' }}
          />
        ) : (
          <pre style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', color: '#d4d4d4', overflowX: 'auto', border: '1px solid #444', minHeight: '150px', fontFamily: 'monospace', margin: 0 }}>
            {generatedAiConfig ? formatConfigText(generatedAiConfig) : formatConfigText(getPlaceholderText())}
          </pre>
        )}

        {/* SIMULATE BUTTON */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '15px' }}>
          <button 
            onClick={handleSimulate} 
            disabled={isSimulating || !generatedAiConfig} 
            style={{ 
              padding: '10px 20px', 
              backgroundColor: (isSimulating || !generatedAiConfig) ? '#555' : '#007acc', 
              color: (isSimulating || !generatedAiConfig) ? '#aaa' : 'white', 
              border: 'none', 
              borderRadius: '4px', 
              cursor: (isSimulating || !generatedAiConfig) ? 'not-allowed' : 'pointer', 
              fontWeight: 'bold' 
            }}
          >
            {isSimulating ? 'Simulating...' : '🧪 Simulate Changes (--check)'}
          </button>
        </div>
      </div>

      {/* 3. TERMINAL OUTPUT BOX */}
      {(simulationLogs.length > 0 || isSimulating) && (
        <div style={{ backgroundColor: '#000', padding: '15px', borderRadius: '8px', border: '2px solid #555', marginBottom: '20px' }}>
          <h4 style={{ color: '#aaa', margin: '0 0 10px 0', borderBottom: '1px solid #333', paddingBottom: '5px' }}>Terminal Output (Ansible Dry-Run)</h4>
          <div style={{ maxHeight: '300px', overflowY: 'auto', color: '#00ff00', fontFamily: 'monospace', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>
            {simulationLogs.map((log, index) => (
              <div key={index} style={{ minHeight: '1.2em', wordBreak: 'break-all' }}>{log}</div>
            ))}
            {/* Invisible div to force scroll to bottom */}
            <div ref={terminalEndRef} />
          </div>
        </div>
      )}

    </div>
  );
}