import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI.
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    
    // Log the error to local storage so the Support Bundle can grab it later
    try {
      const existingLogs = JSON.parse(localStorage.getItem('vnms_ui_errors') || '[]');
      existingLogs.push({
        time: new Date().toISOString(),
        error: error.toString(),
        stack: errorInfo.componentStack
      });
      // Keep only the last 10 errors to prevent storage bloat
      if (existingLogs.length > 10) existingLogs.shift();
      localStorage.setItem('vnms_ui_errors', JSON.stringify(existingLogs));
    } catch (e) {
      console.error("Failed to save error to local storage", e);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '40px', backgroundColor: '#1e1e1e', color: 'white', minHeight: '100vh', boxSizing: 'border-box' }}>
          <h2 style={{ color: '#f44336', borderBottom: '1px solid #f44336', paddingBottom: '10px' }}>⚠️ VNMS UI Crash Detected</h2>
          <p style={{ fontSize: '1.1rem', color: '#ccc' }}>
            A fatal error occurred in the frontend interface. Please reload the page or generate a support bundle to send to the admin.
          </p>
          <div style={{ backgroundColor: '#000', padding: '20px', borderRadius: '8px', border: '1px solid #333', overflowX: 'auto', marginTop: '20px' }}>
            <h4 style={{ color: '#aaa', margin: '0 0 10px 0' }}>Error Traceback:</h4>
            <details style={{ whiteSpace: 'pre-wrap', color: '#f44336', fontSize: '0.9rem' }}>
              <summary style={{ cursor: 'pointer', color: '#e6a23c', marginBottom: '10px', fontWeight: 'bold' }}>Click to view stack trace</summary>
              {this.state.error && this.state.error.toString()}
              <br /><br />
              <span style={{ color: '#888' }}>{this.state.errorInfo && this.state.errorInfo.componentStack}</span>
            </details>
          </div>
          <button 
            onClick={() => window.location.reload()} 
            style={{ marginTop: '20px', padding: '10px 20px', backgroundColor: '#007acc', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
          >
            ↻ Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;