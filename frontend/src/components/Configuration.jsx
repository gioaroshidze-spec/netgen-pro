import { useState, useRef, useEffect } from 'react';

export default function Configuration({ selectedSwitches, selectedRouters }) {
  const [aiPrompt, setAiPrompt] = useState('');
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [generatedAiConfig, setGeneratedAiConfig] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // --- EXECUTION STATES ---
  const [isSimulating, setIsSimulating] = useState(false);
  const [isPushing, setIsPushing] = useState(false);
  const [terminalLogs, setTerminalLogs] = useState([]);
  const terminalEndRef = useRef(null); 

  // Auto-scroll the terminal to the bottom whenever new logs arrive
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLogs]);

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

  // --- UNIFIED STREAMING ENGINE (SIMULATE & PUSH) ---
  const executeConfig = async (mode) => {
    if (!generatedAiConfig) return alert("Please generate a configuration first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) return alert("Please select target devices from the sidebar.");

    // SAFETY NET: Confirm before pushing live!
    if (mode === 'push') {
      const confirmPush = window.confirm("🚨 WARNING: You are about to push this configuration live to production devices. Are you absolutely sure?");
      if (!confirmPush) return;
      setIsPushing(true);
    } else {
      setIsSimulating(true);
    }

    setTerminalLogs([]); // Clear old logs

    try {
      // Dynamically select the API route based on the mode
      const endpoint = mode === 'push' ? '/configuration/push' : '/configuration/simulate';
      
      const response = await fetch(`http://127.0.0.1:8000${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: aiPrompt,
          config_text: generatedAiConfig,
          switches: selectedSwitches,
          routers: selectedRouters
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Execution failed to start.");
      }

      // Read the stream chunk by chunk
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = ""; 

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); 

        for (let part of parts) {
          if (part.startsWith('data: ')) {
            const cleanText = part.substring(6); 
            setTerminalLogs(prev => [...prev, cleanText]);
          }
        }
      }
    } catch (err) {
      console.error(err);
      setTerminalLogs(prev => [...prev, `\n[ERROR]: ${err.message}`]);
    } finally {
      if (mode === 'push') setIsPushing(false);
      else setIsSimulating(false);
    }
  };

  // Default placeholder text in valid JSON format
  const getPlaceholderText = () => {
    if (selectedSwitches.length > 0 || selectedRouters.length > 0) {
      return `{\n  "//_info": "Ready to generate JSON Data Model for:",\n  "//_switches": "${selectedSwitches.join(', ') || 'None'}",\n  "//_routers": "${selectedRouters.join(', ') || 'None'}"\n}`;
    }
    return `{\n  "//_info": "Please select target devices from the sidebar and enter a prompt..."\n}`;
  };

  const isBusy = isSimulating || isPushing || !generatedAiConfig;

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
            disabled={isAiGenerating || isPushing || isSimulating} 
            style={{ padding: '10px 20px', backgroundColor: (isAiGenerating || isPushing || isSimulating) ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: (isAiGenerating || isPushing || isSimulating) ? 'wait' : 'pointer', fontWeight: 'bold' }}
          >
            {isAiGenerating ? 'Generating...' : 'Generate Logic'}
          </button>
        </div>
      </div>
      
      {/* 2. CONFIGURATION BOX */}
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ margin: 0 }}>Generated Configuration Model</h3>
          
          <button 
            onClick={() => setIsEditing(!isEditing)}
            disabled={!generatedAiConfig && !isEditing}
            style={{ padding: '6px 15px', backgroundColor: isEditing ? '#4caf50' : '#e6a23c', color: isEditing ? 'white' : 'black', border: 'none', borderRadius: '4px', cursor: (!generatedAiConfig && !isEditing) ? 'not-allowed' : 'pointer', fontWeight: 'bold', fontSize: '0.9rem' }}
          >
            {isEditing ? '💾 Save Changes' : '✏️ Edit Config'}
          </button>
        </div>

        {/* CONDITIONALLY RENDER TEXTAREA OR PRE */}
        {isEditing ? (
          <textarea 
            value={generatedAiConfig}
            onChange={(e) => setGeneratedAiConfig(e.target.value)}
            style={{ width: '100%', minHeight: '300px', backgroundColor: '#1e1e1e', color: '#d4d4d4', border: '1px solid #007acc', padding: '15px', borderRadius: '4px', resize: 'vertical', fontFamily: 'monospace', outline: 'none' }}
          />
        ) : (
          <pre style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', color: '#569cd6', overflowX: 'auto', border: '1px solid #444', minHeight: '300px', fontFamily: 'monospace', margin: 0 }}>
            {generatedAiConfig ? generatedAiConfig : getPlaceholderText()}
          </pre>
        )}

        {/* ACTION BUTTONS (SIMULATE & PUSH) */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '15px', gap: '15px' }}>
          <button 
            onClick={() => executeConfig('simulate')} 
            disabled={isBusy} 
            style={{ 
              padding: '10px 20px', 
              backgroundColor: isBusy ? '#555' : '#007acc', 
              color: isBusy ? '#aaa' : 'white', 
              border: 'none', 
              borderRadius: '4px', 
              cursor: isBusy ? 'not-allowed' : 'pointer', 
              fontWeight: 'bold' 
            }}
          >
            {isSimulating ? 'Simulating...' : '🧪 Simulate Changes (--check)'}
          </button>
          
          <button 
            onClick={() => executeConfig('push')} 
            disabled={isBusy} 
            style={{ 
              padding: '10px 20px', 
              backgroundColor: isBusy ? '#555' : '#d32f2f', // Aggressive Red for Production Push!
              color: isBusy ? '#aaa' : 'white', 
              border: 'none', 
              borderRadius: '4px', 
              cursor: isBusy ? 'not-allowed' : 'pointer', 
              fontWeight: 'bold' 
            }}
          >
            {isPushing ? 'Deploying...' : '🚀 Push to Production'}
          </button>
        </div>
      </div>

      {/* 3. TERMINAL OUTPUT BOX */}
      {(terminalLogs.length > 0 || isSimulating || isPushing) && (
        <div style={{ backgroundColor: '#000', padding: '15px', borderRadius: '8px', border: '2px solid #555', marginBottom: '20px' }}>
          <h4 style={{ color: '#aaa', margin: '0 0 10px 0', borderBottom: '1px solid #333', paddingBottom: '5px' }}>Terminal Output</h4>
          <div style={{ maxHeight: '600px', overflowY: 'auto', color: '#00ff00', fontFamily: 'monospace', fontSize: '0.9rem', whiteSpace: 'pre-wrap' }}>
            {terminalLogs.map((log, index) => (
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