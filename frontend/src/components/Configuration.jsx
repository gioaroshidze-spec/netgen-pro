import { useState, useRef, useEffect } from 'react';

// --- DYNAMIC API ROUTING ---
const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export default function Configuration({ selectedSwitches, selectedRouters, loadedTemplate, setLoadedTemplate, userRole }) {
  const [aiPrompt, setAiPrompt] = useState('');
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [generatedAiConfig, setGeneratedAiConfig] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  // --- TEMPLATE SAVING STATES ---
  const [templateName, setTemplateName] = useState('');
  const [templateCategory, setTemplateCategory] = useState('Switching');
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);

  // --- EXECUTION STATES ---
  const [isSimulating, setIsSimulating] = useState(false);
  const [isPushing, setIsPushing] = useState(false);
  const [terminalLogs, setTerminalLogs] = useState([]);
  const terminalEndRef = useRef(null); 

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLogs]);

  // Load the template payload into the editor if a template is loaded
  useEffect(() => {
    if (loadedTemplate && loadedTemplate.payload) {
      setGeneratedAiConfig(JSON.stringify(loadedTemplate.payload, null, 2));
    }
  }, [loadedTemplate]);

  const handleGenerateConfig = () => {
    if (!aiPrompt) return alert("Please enter a prompt first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) {
      if(!window.confirm("No target devices selected. Generate general configuration anyway?")) return;
    }

    setIsAiGenerating(true);
    fetch(`${API_BASE}/configuration/generate`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
       },
      body: JSON.stringify({
        prompt: aiPrompt,
        switches: selectedSwitches,
        routers: selectedRouters,
        base_template: loadedTemplate ? loadedTemplate.payload : null 
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

  const handleSaveTemplate = () => {
    if (!templateName) return alert("Please provide a name for the template.");
    if (!generatedAiConfig) return alert("No configuration to save.");

    let parsedPayload;
    try {
      parsedPayload = JSON.parse(generatedAiConfig);
    } catch (e) {
      return alert("Invalid JSON. Please fix any syntax errors before saving as a template.");
    }

    setIsSavingTemplate(true);
    fetch(`${API_BASE}/templates/`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json', 
        'Authorization': `Bearer ${localStorage.getItem('token')}`
       },
      body: JSON.stringify({
        name: templateName,
        category: templateCategory,
        payload: parsedPayload
      })
    })
    .then(async res => {
      if (!res.ok) throw new Error("Failed to save template");
      return res.json();
    })
    .then(() => {
      alert("Template saved successfully! AI generated the description.");
      setTemplateName('');
      setIsSavingTemplate(false);
    })
    .catch(err => {
      console.error(err);
      alert("Failed to save template.");
      setIsSavingTemplate(false);
    });
  };

  const executeConfig = async (mode) => {
    if (!generatedAiConfig) return alert("Please generate a configuration first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) return alert("Please select target devices from the sidebar.");

    if (mode === 'push') {
      const confirmPush = window.confirm("🚨 WARNING: You are about to push this configuration live to production devices. Are you absolutely sure?");
      if (!confirmPush) return;
      setIsPushing(true);
    } else {
      setIsSimulating(true);
    }

    setTerminalLogs([]);

    try {
      const endpoint = mode === 'push' ? '/configuration/push' : '/configuration/simulate';
      
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json', 
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
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

  const getPlaceholderText = () => {
    if (selectedSwitches.length > 0 || selectedRouters.length > 0) {
      return `{\n  "//_info": "Ready to generate JSON Data Model for:",\n  "//_switches": "${selectedSwitches.join(', ') || 'None'}",\n  "//_routers": "${selectedRouters.join(', ') || 'None'}"\n}`;
    }
    return `{\n  "//_info": "Please select target devices from the sidebar and enter a prompt..."\n}`;
  };

  const isBusy = isSimulating || isPushing || !generatedAiConfig;
  const canExecute = userRole === 'admin' || (userRole === 'viewer' && loadedTemplate !== null);

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      {/* ACTIVE TEMPLATE BANNER */}
      {loadedTemplate && (
        <div style={{ backgroundColor: '#007acc15', border: '1px solid #007acc', padding: '15px', borderRadius: '8px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong style={{ color: '#007acc', fontSize: '1.1rem' }}>Template Active: {loadedTemplate.name}</strong>
            <div style={{ fontSize: '0.9rem', color: '#ccc', marginTop: '5px' }}>{loadedTemplate.description}</div>
            <div style={{ fontSize: '0.8rem', color: '#888', marginTop: '5px' }}>The AI will map this template to the targets selected in the sidebar based on your prompt.</div>
          </div>
          <button onClick={() => { setLoadedTemplate(null); setGeneratedAiConfig(''); setAiPrompt(''); }} style={{ padding: '8px 15px', backgroundColor: 'transparent', color: '#007acc', border: '1px solid #007acc', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
            Clear Template
          </button>
        </div>
      )}

      <h2>AI Configuration Engine</h2>
      
      {/* 1. PROMPT BOX */}
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
        <textarea 
          placeholder={loadedTemplate ? "e.g., 'Apply this template but use VLAN 200 and set the interface range to g1/0/1 - 10'" : "e.g., 'Configure VLAN 10 named GUEST and VLAN 20 named IOT...'"}
          value={aiPrompt} 
          onChange={(e) => setAiPrompt(e.target.value)} 
          style={{ width: '100%', height: '100px', backgroundColor: '#1e1e1e', color: '#fff', border: '1px solid #444', padding: '15px', borderRadius: '4px', resize: 'vertical' }} 
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
          <button 
            onClick={handleGenerateConfig} 
            disabled={isAiGenerating || isPushing || isSimulating || !canExecute} 
            title={!canExecute ? "Load a template to enable AI Generation" : ""}
            style={{ padding: '10px 20px', backgroundColor: (isAiGenerating || isPushing || isSimulating || !canExecute) ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: (isAiGenerating || isPushing || isSimulating || !canExecute) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
          >
            {isAiGenerating ? 'Generating...' : (loadedTemplate ? 'Adapt Template Logic' : 'Generate Logic')}
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
            {isEditing ? '💾 Lock JSON' : '✏️ Edit Config'}
          </button>
        </div>

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

        {/* SAVE AS TEMPLATE FORM */}
        {generatedAiConfig && !loadedTemplate && (
          <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px dashed #444', display: 'flex', gap: '15px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#aaa', marginBottom: '5px' }}>Save as Template</label>
              <input type="text" value={templateName} onChange={e => setTemplateName(e.target.value)} placeholder="e.g., Access Port Baseline" style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }} />
            </div>
            <div style={{ width: '150px' }}>
              <select value={templateCategory} onChange={e => setTemplateCategory(e.target.value)} style={{ width: '100%', padding: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #444', borderRadius: '4px' }}>
                <option value="Switching">Switching</option>
                <option value="Routing">Routing</option>
                <option value="Security">Security</option>
                <option value="Golden Image">Golden Image</option>
              </select>
            </div>
            <button onClick={handleSaveTemplate} disabled={isSavingTemplate || !templateName} style={{ padding: '10px 20px', backgroundColor: (isSavingTemplate || !templateName) ? '#555' : '#4caf50', color: 'white', border: 'none', borderRadius: '4px', cursor: (isSavingTemplate || !templateName) ? 'not-allowed' : 'pointer', fontWeight: 'bold', height: '39px' }}>
              {isSavingTemplate ? 'Saving...' : '💾 Save Template'}
            </button>
          </div>
        )}

        {/* ACTION BUTTONS (SIMULATE & PUSH) */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px', gap: '15px' }}>
          <button 
            onClick={() => executeConfig('simulate')} 
            disabled={isBusy || !canExecute} 
            title={!canExecute ? "Load a template to enable simulation" : ""}
            style={{ padding: '10px 20px', backgroundColor: (isBusy || !canExecute) ? '#555' : '#007acc', color: (isBusy || !canExecute) ? '#aaa' : 'white', border: 'none', borderRadius: '4px', cursor: (isBusy || !canExecute) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
          >
            {isSimulating ? 'Simulating...' : '🧪 Simulate Changes (--check)'}
          </button>
          <button 
            onClick={() => executeConfig('push')} 
            disabled={isBusy || !canExecute} 
            title={!canExecute ? "Load a template to enable production push" : ""}
            style={{ padding: '10px 20px', backgroundColor: (isBusy || !canExecute) ? '#555' : '#d32f2f', color: (isBusy || !canExecute) ? '#888' : 'white', border: 'none', borderRadius: '4px', cursor: (isBusy || !canExecute) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
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
            <div ref={terminalEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}