import { useState } from 'react';

export default function Configuration({ selectedSwitches, selectedRouters }) {
  const [aiPrompt, setAiPrompt] = useState('');
  const [isAiGenerating, setIsAiGenerating] = useState(false);
  const [generatedAiConfig, setGeneratedAiConfig] = useState('');
  const [isEditing, setIsEditing] = useState(false); // NEW STATE FOR EDIT MODE

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
      setIsEditing(false); // Ensure we are in read-only mode after generating
    })
    .catch(err => { 
      console.error(err); 
      alert(`Generation Failed: ${err.message}`); 
      setIsAiGenerating(false); 
    });
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

  // Default placeholder text when nothing is generated yet
  const getPlaceholderText = () => {
    if (selectedSwitches.length > 0 || selectedRouters.length > 0) {
      return `! Ready to generate config for:\n! Switches: ${selectedSwitches.join(', ') || 'None'}\n! Routers: ${selectedRouters.join(', ') || 'None'}`;
    }
    return `! Please select target devices from the sidebar and enter a prompt...`;
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <h2>AI Configuration Engine</h2>
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
      
      <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: '1px solid #333', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h3 style={{ margin: 0 }}>Generated Configuration</h3>
          
          {/* EDIT / SAVE TOGGLE BUTTON */}
          <button 
            onClick={() => setIsEditing(!isEditing)}
            disabled={!generatedAiConfig && !isEditing} // Only allow edit if there is text
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
            style={{ width: '100%', minHeight: '200px', backgroundColor: '#1e1e1e', color: '#d4d4d4', border: '1px solid #007acc', padding: '15px', borderRadius: '4px', resize: 'vertical', fontFamily: 'monospace', outline: 'none' }}
          />
        ) : (
          <pre style={{ backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '4px', color: '#d4d4d4', overflowX: 'auto', border: '1px solid #444', minHeight: '150px', fontFamily: 'monospace', margin: 0 }}>
            {generatedAiConfig ? formatConfigText(generatedAiConfig) : formatConfigText(getPlaceholderText())}
          </pre>
        )}
      </div>
    </div>
  );
}