import { useState } from 'react';
import { analyzeSession } from './api/client';
import Dashboard from './features/analysis/Dashboard';
import UploadScreen from './features/analysis/UploadScreen';

export default function App() {
  const [report, setReport] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleFileSelected = async (file) => {
    setIsLoading(true);
    setError('');
    try {
      setReport(await analyzeSession(file));
    } catch (problem) {
      setReport(null);
      setError(problem?.message || 'Не удалось связаться с бэкендом.');
    } finally {
      setIsLoading(false);
    }
  };

  const reset = () => {
    setReport(null);
    setError('');
  };

  if (!report) {
    return <UploadScreen onFileSelected={handleFileSelected} isLoading={isLoading} error={error} />;
  }
  return <Dashboard report={report} onReset={reset} />;
}
