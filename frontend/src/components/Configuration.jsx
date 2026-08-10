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
  const [changeId, setChangeId] = useState(null);
  const [simulationStatus, setSimulationStatus] = useState(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [isAuthorizingOverride, setIsAuthorizingOverride] = useState(false);
  const [changeStatus, setChangeStatus] = useState(null);
  const [rollbackReason, setRollbackReason] = useState('');
  const [isReverifying, setIsReverifying] = useState(false);
  const [isAuthorizingRollback, setIsAuthorizingRollback] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const changeIdRef = useRef(null);
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

  useEffect(() => {
    setChangeId(null);
    setSimulationStatus(null);
    setOverrideReason('');
    setChangeStatus(null);
    setRollbackReason('');
  }, [selectedSwitches, selectedRouters, loadedTemplate]);

  const invalidateSimulation = () => {
    changeIdRef.current = null;
    setChangeId(null);
    setSimulationStatus(null);
    setOverrideReason('');
    setChangeStatus(null);
    setRollbackReason('');
  };

  const refreshChangeStatus = async (id = changeIdRef.current) => {
    if (!id) return null;
    const response = await fetch(`${API_BASE}/configuration/changes/${id}`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not refresh change status.');
    if (changeIdRef.current === id) setChangeStatus(data);
    return data;
  };

  const reverifyChange = async () => {
    setIsReverifying(true);
    try {
      const response = await fetch(`${API_BASE}/configuration/changes/${changeId}/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: '{}'
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Re-verification failed.');
      await refreshChangeStatus(changeId);
    } catch (err) {
      setTerminalLogs(prev => [...prev, `[ERROR]: ${err.message}`]);
    } finally { setIsReverifying(false); }
  };

  const authorizeRollback = async () => {
    if (rollbackReason.trim().length < 10) return;
    setIsAuthorizingRollback(true);
    try {
      const response = await fetch(`${API_BASE}/configuration/changes/${changeId}/authorize-rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ reason: rollbackReason.trim() })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Rollback authorization failed.');
      await refreshChangeStatus(changeId);
    } catch (err) {
      setTerminalLogs(prev => [...prev, `[ERROR]: ${err.message}`]);
    } finally { setIsAuthorizingRollback(false); }
  };

  const executeRollback = async () => {
    const rollbackId = changeStatus?.rollback?.rollback_id;
    if (!rollbackId) return;
    const warning = 'HIGH-RISK FULL CONFIGURATION ROLLBACK\n\nThis operation may replace the full device configuration.\nManagement connectivity may be interrupted.\nOut-of-band/console access is recommended.\n\nExecute the authorized rollback?';
    if (!window.confirm(warning)) return;
    setIsRollingBack(true);
    try {
      const response = await fetch(`${API_BASE}/configuration/changes/${changeId}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ rollback_id: rollbackId })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Rollback failed.');
      await refreshChangeStatus(changeId);
    } catch (err) {
      setTerminalLogs(prev => [...prev, `[ERROR]: ${err.message}`]);
      await refreshChangeStatus(changeId).catch(() => {});
    } finally { setIsRollingBack(false); }
  };

  const handleGenerateConfig = () => {
    if (!aiPrompt) return alert("Please enter a prompt first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) {
      if(!window.confirm("No target devices selected. Generate general configuration anyway?")) return;
    }

    setIsAiGenerating(true);
    invalidateSimulation();
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
      invalidateSimulation();
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
    } catch {
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
        payload: parsedPayload,
        prompt: aiPrompt  // <-- INJECTED PROMPT METADATA HERE
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

  const authorizeOverride = async () => {
    if (!changeId || overrideReason.trim().length < 10) return;
    const authorizingChangeId = changeId;
    setIsAuthorizingOverride(true);
    try {
      const response = await fetch(`${API_BASE}/configuration/changes/${changeId}/override-simulation`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ override_reason: overrideReason.trim() })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Override authorization failed.');
      if (changeIdRef.current === authorizingChangeId) {
        setSimulationStatus('override_authorized');
        setTerminalLogs(prev => [...prev, data.message || 'Admin Override Authorized — Production Push Available']);
      }
    } catch (err) {
      setTerminalLogs(prev => [...prev, `[ERROR]: ${err.message}`]);
    } finally {
      setIsAuthorizingOverride(false);
    }
  };

  const executeConfig = async (mode) => {
    if (!generatedAiConfig) return alert("Please generate a configuration first.");
    if (selectedSwitches.length === 0 && selectedRouters.length === 0) return alert("Please select target devices from the sidebar.");

    if (mode === 'push') {
      if (!canPush) return alert("Administrator privileges required for production deployment.");
      if (!changeId) return alert("Run a simulation before production deployment.");
      const message = simulationStatus === 'override_authorized'
        ? "WARNING: This deployment uses an authorized failed-simulation override.\n\nVNMS will capture mandatory Pre_Config backups, then deploy the exact stored proposal. Continue with elevated-risk deployment?"
        : "🚨 WARNING: VNMS will capture Pre_Config backups in the server archive, then deploy the exact simulated proposal. Continue?";
      const confirmPush = window.confirm(message);
      if (!confirmPush) return;
      setIsPushing(true);
    } else {
      setIsSimulating(true);
    }

    setTerminalLogs([]);

    try {
      const endpoint = mode === 'push' ? '/configuration/push' : '/configuration/simulate';
      const requestBody = mode === 'push'
        ? { change_id: changeId }
        : { prompt: aiPrompt, config_text: generatedAiConfig, switches: selectedSwitches, routers: selectedRouters,
            source_template: loadedTemplate ? loadedTemplate.name : null };
      
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json', 
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        const errData = await response.json();
        if (response.status === 403) {
          throw new Error(errData.detail || "Administrator privileges required for production deployment.");
        }
        throw new Error(errData.detail || "Execution failed to start.");
      }

      const reader = response.body.getReader();
      if (mode === 'simulate') {
        const issuedChangeId = response.headers.get('X-VNMS-Change-ID');
        changeIdRef.current = issuedChangeId;
        setChangeId(issuedChangeId);
      }
      const decoder = new TextDecoder("utf-8");
      let buffer = ""; 
      let completeOutput = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const decoded = decoder.decode(value, { stream: true });
        buffer += decoded;
        completeOutput += decoded;
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); 

        for (let part of parts) {
          if (part.startsWith('data: ')) {
            const cleanText = part.substring(6); 
            setTerminalLogs(prev => [...prev, cleanText]);
          }
        }
      }
      if (mode === 'simulate') {
        const passed = completeOutput.includes('PLAY RECAP') && completeOutput.includes('PLAYBOOK COMPLETE: No errors detected.')
          && !/failed=[1-9]\d*|unreachable=[1-9]\d*|fatal:/i.test(completeOutput);
        setSimulationStatus(passed ? 'passed' : 'failed');
      } else {
        setTerminalLogs(prev => [...prev, 'Refreshing durable post-change verification status...']);
        await refreshChangeStatus(changeId);
        setSimulationStatus(null);
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
  const canUseTemplateWorkflow = userRole === 'admin' || (userRole === 'viewer' && loadedTemplate !== null);
  const canSimulate = canUseTemplateWorkflow;
  const canPush = userRole === 'admin';

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
          <button onClick={() => { setLoadedTemplate(null); setGeneratedAiConfig(''); setAiPrompt(''); invalidateSimulation(); }} style={{ padding: '8px 15px', backgroundColor: 'transparent', color: '#007acc', border: '1px solid #007acc', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}>
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
            disabled={isAiGenerating || isPushing || isSimulating || !canUseTemplateWorkflow} 
            title={!canUseTemplateWorkflow ? "Load a template to enable AI Generation" : ""}
            style={{ padding: '10px 20px', backgroundColor: (isAiGenerating || isPushing || isSimulating || !canUseTemplateWorkflow) ? '#555' : '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: (isAiGenerating || isPushing || isSimulating || !canUseTemplateWorkflow) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
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
            onChange={(e) => { setGeneratedAiConfig(e.target.value); invalidateSimulation(); }}
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
            disabled={isBusy || !canSimulate} 
            title={!canSimulate ? "Load a template to enable simulation" : ""}
            style={{ padding: '10px 20px', backgroundColor: (isBusy || !canSimulate) ? '#555' : '#007acc', color: (isBusy || !canSimulate) ? '#aaa' : 'white', border: 'none', borderRadius: '4px', cursor: (isBusy || !canSimulate) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
          >
            {isSimulating ? 'Simulating...' : '🧪 Simulate Changes (--check)'}
          </button>
          {canPush && (
            <button 
              onClick={() => executeConfig('push')} 
              disabled={isBusy || !['passed', 'override_authorized'].includes(simulationStatus) || !changeId}
              style={{ padding: '10px 20px', backgroundColor: (isBusy || !['passed', 'override_authorized'].includes(simulationStatus) || !changeId) ? '#555' : '#d32f2f', color: (isBusy || !['passed', 'override_authorized'].includes(simulationStatus) || !changeId) ? '#888' : 'white', border: 'none', borderRadius: '4px', cursor: (isBusy || !['passed', 'override_authorized'].includes(simulationStatus) || !changeId) ? 'not-allowed' : 'pointer', fontWeight: 'bold' }}
            >
              {isPushing ? 'Deploying...' : '🚀 Push to Production'}
            </button>
          )}
        </div>
        {canPush && simulationStatus === 'failed' && changeId && (
          <div style={{ marginTop: '15px', padding: '15px', border: '1px solid #d32f2f', borderRadius: '4px', backgroundColor: '#d32f2f15' }}>
            <strong style={{ color: '#ff6b6b' }}>Simulation failed — production is blocked by default.</strong>
            <textarea value={overrideReason} onChange={e => setOverrideReason(e.target.value)} maxLength={1000}
              placeholder="Required: explain why this failed simulation is safe to override"
              style={{ width: '100%', minHeight: '80px', marginTop: '10px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #d32f2f', padding: '10px' }} />
            <button onClick={authorizeOverride} disabled={isAuthorizingOverride || overrideReason.trim().length < 10}
              style={{ marginTop: '10px', padding: '10px 20px', backgroundColor: '#d32f2f', color: 'white', border: 'none', borderRadius: '4px', fontWeight: 'bold' }}>
              {isAuthorizingOverride ? 'Authorizing...' : 'Authorize Override'}
            </button>
          </div>
        )}
        {canPush && simulationStatus === 'override_authorized' && (
          <div style={{ marginTop: '15px', padding: '12px', border: '1px solid #e6a23c', borderRadius: '4px', color: '#e6a23c' }}>
            Admin Override Authorized — Production Push Available
          </div>
        )}
      </div>

      {changeStatus && ['verified', 'verification_failed', 'verification_error', 'deployment_failed'].includes(changeStatus.status) && (
        <div style={{ backgroundColor: '#252526', padding: '20px', borderRadius: '8px', border: `1px solid ${changeStatus.status === 'verified' ? '#4caf50' : '#d32f2f'}`, marginBottom: '20px' }}>
          {changeStatus.status === 'verified' && <><h3 style={{ color: '#4caf50' }}>Post-Change Verification Passed</h3><p>All target devices are converged.</p></>}
          {changeStatus.status === 'verification_failed' && <><h3 style={{ color: '#ff6b6b' }}>Post-Change Verification Failed</h3><p>One or more devices still differ from the approved desired state.</p></>}
          {changeStatus.status === 'verification_error' && <><h3 style={{ color: '#e6a23c' }}>Post-Change Verification Inconclusive</h3><p>VNMS could not reliably determine final state.</p></>}
          {changeStatus.status === 'deployment_failed' && <><h3 style={{ color: '#ff6b6b' }}>Production Deployment Failed</h3><p><strong>Partial deployment may have occurred.</strong> Rollback will restore the full pre-change configuration.</p></>}
          {changeStatus.latest_verification?.per_device_results && (
            <div style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
              {Object.entries(changeStatus.latest_verification.per_device_results).map(([host, result]) => (
                <div key={host}>{host}: {result.status} (ok={result.ok ?? '-'} changed={result.changed ?? '-'} unreachable={result.unreachable ?? '-'} failed={result.failed ?? '-'})</div>
              ))}
              <div style={{ color: '#aaa', marginTop: '8px' }}>Privileged EXEC side effects are not state-verified by this configuration convergence check.</div>
            </div>
          )}
          {canPush && ['verified', 'verification_failed', 'verification_error'].includes(changeStatus.status) && (
            <button onClick={reverifyChange} disabled={isReverifying} style={{ marginTop: '12px', padding: '9px 16px' }}>
              {isReverifying ? 'Re-verifying...' : 'Re-run Deterministic Verification'}
            </button>
          )}
          {canPush && changeStatus.rollback?.eligible && !changeStatus.rollback.authorized && !changeStatus.rollback.status && (
            <div style={{ marginTop: '18px', borderTop: '1px solid #555', paddingTop: '15px' }}>
              <strong>Controlled Rollback Authorization</strong>
              <p style={{ color: '#e6a23c' }}>Full restore can interrupt management connectivity. VNMS history cannot detect every out-of-band/manual change.</p>
              <textarea value={rollbackReason} onChange={e => setRollbackReason(e.target.value)} maxLength={1000}
                placeholder="Required rollback reason (10–1000 characters)"
                style={{ width: '100%', minHeight: '80px', backgroundColor: '#1e1e1e', color: 'white', border: '1px solid #e6a23c', padding: '10px' }} />
              <button onClick={authorizeRollback} disabled={isAuthorizingRollback || rollbackReason.trim().length < 10}
                style={{ marginTop: '10px', padding: '10px 18px', backgroundColor: '#e6a23c', border: 'none', fontWeight: 'bold' }}>
                {isAuthorizingRollback ? 'Authorizing...' : 'Authorize Rollback'}
              </button>
            </div>
          )}
          {canPush && changeStatus.rollback?.authorized && (
            <div style={{ marginTop: '18px', border: '2px solid #d32f2f', padding: '15px' }}>
              <strong style={{ color: '#ff6b6b' }}>Rollback Authorized</strong>
              <p>This operation may replace the full device configuration. Management connectivity may be interrupted. Out-of-band/console access is recommended.</p>
              <button onClick={executeRollback} disabled={isRollingBack}
                style={{ padding: '10px 18px', backgroundColor: '#d32f2f', color: 'white', border: 'none', fontWeight: 'bold' }}>
                {isRollingBack ? 'Executing Rollback...' : 'Execute Rollback'}
              </button>
            </div>
          )}
          {changeStatus.rollback?.status && changeStatus.rollback.status !== 'authorized' && (
            <div style={{ marginTop: '15px' }}><strong>Rollback status:</strong> {changeStatus.rollback.status}</div>
          )}
        </div>
      )}

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
