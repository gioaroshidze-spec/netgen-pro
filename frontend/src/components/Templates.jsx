import React, { useState, useEffect } from 'react';

const API_URL = 'http://127.0.0.1:8000/templates/';

export default function Templates({ setActiveTab, setLoadedTemplate }) {
  const [templates, setTemplates] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  const fetchTemplates = () => {
    setIsLoading(true);
    fetch(API_URL, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } // <-- TOKEN INJECTED
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to fetch templates");
        return res.json();
      })
      .then(data => {
        setTemplates(data);
        setIsLoading(false);
      })
      .catch(err => {
        console.error(err);
        setIsLoading(false);
      });
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  const handleDelete = (id) => {
    if (!window.confirm("Are you sure you want to delete this template?")) return;
    fetch(`${API_URL}${id}`, { 
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` } // <-- TOKEN INJECTED
    })
      .then(() => fetchTemplates())
      .catch(err => console.error("Failed to delete", err));
  };

  const handleLoad = (template) => {
    setLoadedTemplate(template);
    setActiveTab('Configuration');
  };

  const toggleRow = (id) => {
    setExpandedRow(prev => prev === id ? null : id);
  };

  const getCategoryColor = (category) => {
    switch(category.toLowerCase()) {
      case 'security': return '#f44336';
      case 'routing': return '#007acc';
      case 'golden image': return '#e6a23c';
      case 'switching': return '#4caf50';
      default: return '#aaa';
    }
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Configuration Templates</h2>
        <button onClick={fetchTemplates} style={{ padding: '8px 15px', backgroundColor: '#333', color: 'white', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer' }}>
          {isLoading ? '↻ Loading...' : '↻ Refresh Data'}
        </button>
      </div>

      <div style={{ backgroundColor: '#252526', borderRadius: '8px', border: '1px solid #333', overflow: 'hidden' }}>
        <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
          <thead style={{ backgroundColor: '#333' }}>
            <tr>
              <th style={{ padding: '15px' }}>Name</th>
              <th style={{ padding: '15px' }}>Category</th>
              <th style={{ padding: '15px', width: '40%' }}>AI Description</th>
              <th style={{ padding: '15px' }}>Created</th>
              <th style={{ padding: '15px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {templates.length === 0 ? (
              <tr><td colSpan="5" style={{ padding: '30px', textAlign: 'center', color: '#666' }}>No templates saved yet.</td></tr>
            ) : templates.map((tmpl) => (
              <React.Fragment key={tmpl.id}>
                <tr style={{ borderBottom: '1px solid #444', backgroundColor: expandedRow === tmpl.id ? '#2a2a2a' : 'transparent', transition: 'background-color 0.2s' }}>
                  <td style={{ padding: '15px', fontWeight: 'bold' }}>{tmpl.name}</td>
                  <td style={{ padding: '15px' }}>
                    <span style={{ padding: '4px 8px', borderRadius: '4px', backgroundColor: `${getCategoryColor(tmpl.category)}22`, color: getCategoryColor(tmpl.category), fontWeight: 'bold', fontSize: '0.8rem', textTransform: 'uppercase' }}>
                      {tmpl.category}
                    </span>
                  </td>
                  <td style={{ padding: '15px', color: '#aaa', fontSize: '0.9rem', fontStyle: 'italic' }}>"{tmpl.description}"</td>
                  <td style={{ padding: '15px', color: '#888', fontSize: '0.85rem' }}>{new Date(tmpl.created_at).toLocaleDateString()}</td>
                  <td style={{ padding: '15px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                    <button onClick={() => toggleRow(tmpl.id)} style={{ padding: '6px 10px', backgroundColor: '#333', color: '#fff', border: '1px solid #555', borderRadius: '4px', cursor: 'pointer', marginRight: '5px' }}>
                      {expandedRow === tmpl.id ? 'Close' : 'View'}
                    </button>
                    <button onClick={() => handleLoad(tmpl)} style={{ padding: '6px 10px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', marginRight: '5px', fontWeight: 'bold' }}>
                      Load
                    </button>
                    <button onClick={() => handleDelete(tmpl.id)} style={{ padding: '6px 10px', backgroundColor: 'transparent', color: '#f44336', border: '1px solid #f44336', borderRadius: '4px', cursor: 'pointer' }}>
                      Delete
                    </button>
                  </td>
                </tr>

                {expandedRow === tmpl.id && (
                  <tr style={{ backgroundColor: '#1a1a1a', borderBottom: '2px solid #007acc' }}>
                    <td colSpan="5" style={{ padding: '20px' }}>
                      <strong style={{ color: '#aaa', display: 'block', marginBottom: '10px' }}>Template JSON Payload:</strong>
                      <pre style={{ backgroundColor: '#000', padding: '15px', borderRadius: '4px', border: '1px solid #333', color: '#569cd6', overflowX: 'auto', maxHeight: '300px', fontSize: '0.85rem', margin: 0 }}>
                        {JSON.stringify(tmpl.payload, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}