import React, { useState } from 'react';



const Dashboard = () => {

  const [isLoaded, setIsLoaded] = useState(false);

  const [isLoading, setIsLoading] = useState(false);

  const [sessionData, setSessionData] = useState(null);

  const [activeStep, setActiveStep] = useState(null);

  const [activeTab, setActiveTab] = useState('current');



  // Отправка файла на бэкенд

  const handleFileUpload = async (event) => {

    const file = event.target.files[0];

    if (!file) return;



    setIsLoading(true);

    const formData = new FormData();

    formData.append('file', file); // Ключ 'file' должен совпадать с тем, что ждет бэкенд (FastAPI/Flask)



    try {

      // ВНИМАНИЕ: Замени порт 8000 на тот, где крутится ваш Python-сервер

      const response = await fetch('http://127.0.0.1:8000/api/analyze', {

        method: 'POST',

        body: formData,

      });

      

      if (!response.ok) {

        throw new Error(`Ошибка сервера: ${response.status}`);

      }

      

      const data = await response.json();

      setSessionData(data);

      setIsLoaded(true);

    } catch (error) {

      console.error("Ошибка при отправке файла:", error);

      alert("Не удалось связаться с бэкендом. Проверьте, запущен ли Python-сервер и настроен ли CORS.");

    } finally {

      setIsLoading(false);

    }

  };



  // Генерация и скачивание Markdown файла

  const downloadArtifact = () => {

    if (!sessionData?.artifactText) return;

    const blob = new Blob([sessionData.artifactText], { type: 'text/markdown' });

    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');

    a.href = url;

    a.download = 'CLAUDE.md';

    document.body.appendChild(a);

    a.click();

    document.body.removeChild(a);

    URL.revokeObjectURL(url);

  };



  const getStatusColor = (type) => {

    switch(type) {

      case 'error': return 'text-red-500 bg-red-500/10 border-red-500/20';

      case 'loop': return 'text-red-400 bg-red-400/10 border-red-400/20';

      case 'human': return 'text-amber-500 bg-amber-500/10 border-amber-500/20';

      case 'success': return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';

      default: return 'text-zinc-400 bg-zinc-800 border-zinc-700';

    }

  };



  const getTimelineColor = (type) => {

    switch(type) {

      case 'error': return 'bg-red-500';

      case 'loop': return 'bg-red-600';

      case 'human': return 'bg-amber-500';

      case 'success': return 'bg-emerald-500/80';

      default: return 'bg-zinc-600';

    }

  };



  // Экран загрузки

  if (!isLoaded) {

    return (

      <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-6 text-zinc-300 font-sans">

        <div className="w-full max-w-md p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-2xl flex flex-col items-center">

          <div className="w-12 h-12 mb-6 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center">

            {isLoading ? (

              <svg className="animate-spin h-6 w-6 text-emerald-500" fill="none" viewBox="0 0 24 24">

                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>

                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>

              </svg>

            ) : (

              <span className="text-2xl">📊</span>

            )}

          </div>

          <h1 className="text-xl font-medium text-white mb-2">Анализ сессии агента</h1>

          <p className="text-sm text-zinc-500 text-center mb-8">Загрузите .jsonl лог Claude Code или Codex для диагностики проблем.</p>

          

          <label className={`w-full py-3 px-4 flex justify-center items-center text-white font-medium rounded-lg transition-colors cursor-pointer text-center shadow-md ${isLoading ? 'bg-emerald-800 cursor-wait' : 'bg-emerald-600 hover:bg-emerald-500'}`}>

            {isLoading ? "Анализируем лог..." : "Выбрать .jsonl файл"}

            <input 

              type="file" 

              accept=".jsonl" 

              className="hidden" 

              onChange={handleFileUpload} 

              disabled={isLoading}

            />

          </label>

        </div>

      </div>

    );

  }



  // Основной экран дашборда

  return (

    <div className="min-h-screen bg-zinc-950 text-zinc-300 font-sans selection:bg-zinc-800">

      {/* Top Header */}

      <header className="h-16 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur flex items-center justify-between px-6 sticky top-0 z-10">

        <div className="flex items-center gap-6">

          <div className="text-sm font-mono bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-md text-zinc-400 shadow-sm">

            {sessionData?.summary?.fileName || "log.jsonl"}

          </div>

          <span className="text-sm text-zinc-500 font-medium">Время: {sessionData?.summary?.duration || "N/A"}</span>

        </div>

        <div className="flex items-center gap-6 text-sm">

          <div className="flex flex-col items-end">

            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-0.5">Расход сессии</span>

            <span className="font-mono text-2xl text-emerald-400 font-semibold">{sessionData?.summary?.totalCost || "$0.00"}</span>

          </div>

          <div className="h-10 w-px bg-zinc-800"></div>

          <div className="flex flex-col items-end">

            <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold mb-0.5">Потрачено токенов</span>

            <span className="font-mono text-2xl text-white font-semibold">{sessionData?.summary?.totalTokens || "0"}</span>

          </div>

        </div>

      </header>



      <main className="p-6 max-w-[1600px] mx-auto">

        

        {/* Tabs */}

        <div className="flex gap-6 mb-6 border-b border-zinc-800">

          <button 

            onClick={() => setActiveTab('current')}

            className={`pb-3 text-sm font-medium transition-colors relative ${activeTab === 'current' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}

          >

            Анализ текущей сессии

            {activeTab === 'current' && <div className="absolute bottom-0 left-0 w-full h-0.5 bg-emerald-500 rounded-t-full"></div>}

          </button>

          <button 

            onClick={() => setActiveTab('compare')}

            className={`pb-3 text-sm font-medium transition-colors relative ${activeTab === 'compare' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'}`}

          >

            Сравнение с предыдущей

            {activeTab === 'compare' && <div className="absolute bottom-0 left-0 w-full h-0.5 bg-emerald-500 rounded-t-full"></div>}

          </button>

        </div>



        {activeTab === 'current' ? (

          <div className="grid grid-cols-12 gap-6">

            

            {/* Left Column: Metrics & Timeline */}

            <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">

              

              {/* Metrics Grid */}

              <div className="grid grid-cols-4 gap-4">

                {sessionData?.metrics?.map((m, idx) => (

                  <div key={idx} className="p-5 border border-zinc-800 bg-zinc-900/40 rounded-xl flex flex-col justify-center items-start shadow-sm">

                    <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">{m.label}</span>

                    <span className={`text-4xl font-bold tracking-tight ${m.status === 'critical' ? 'text-red-400' : m.status === 'warning' ? 'text-amber-400' : 'text-white'}`}>

                      {m.value}

                    </span>

                  </div>

                ))}

              </div>



              {/* Enhanced Timeline */}

              <div className="p-6 border border-zinc-800 bg-zinc-900/30 rounded-xl shadow-sm">

                <h2 className="text-sm font-medium text-white mb-5 flex items-center gap-2">

                  <svg className="w-4 h-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">

                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />

                  </svg>

                  Карта сессии

                </h2>

                

                {/* Segmented Timeline Bar */}

                <div className="flex h-10 w-full gap-1 p-1 bg-zinc-950 rounded-lg border border-zinc-800/80 cursor-pointer">

                  {sessionData?.logSteps?.map((step, index) => (

                    <div 

                      key={step.id || index} 

                      onClick={() => setActiveStep(step)}

                      className={`h-full rounded-[3px] transition-all hover:brightness-150 hover:-translate-y-0.5 shadow-sm ${getTimelineColor(step.type)}`}

                      style={{ width: step.width || '10%' }}

                      title={step.action}

                    />

                  ))}

                </div>

                

                <div className="flex justify-between mt-3 text-[10px] text-zinc-500 font-mono uppercase font-bold tracking-widest">

                  <span>Старт</span>

                  <span>Конец сессии</span>

                </div>

              </div>



              {/* Detailed Log Trace */}

              <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl overflow-hidden flex-1 shadow-sm">

                <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/80">

                  <h2 className="text-sm font-medium text-white">Трассировка шагов</h2>

                </div>

                <div className="p-3 space-y-1.5">

                  {sessionData?.logSteps?.map((step, index) => (

                    <div 

                      key={step.id || index}

                      onClick={() => setActiveStep(step)}

                      className={`p-4 rounded-lg text-sm flex items-start gap-4 cursor-pointer transition-all border

                        ${activeStep?.id === step.id ? 'bg-zinc-800 border-zinc-700 shadow-md' : 'bg-transparent border-transparent hover:bg-zinc-800/40'}`}

                    >

                      <span className="text-xs font-mono text-zinc-500 mt-0.5 font-medium">{step.time}</span>

                      <div className="flex-1">

                        <div className="flex items-center gap-3 mb-1.5">

                          <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded shadow-sm border ${getStatusColor(step.type)}`}>

                            {step.type}

                          </span>

                          <span className="font-mono text-xs text-zinc-400 bg-zinc-950 px-2 py-0.5 rounded border border-zinc-800">{step.tool}</span>

                        </div>

                        <p className={activeStep?.id === step.id ? 'text-zinc-100 font-medium' : 'text-zinc-400'}>

                          {step.action}

                        </p>

                      </div>

                      <span className="text-sm font-mono font-bold text-zinc-500">{step.cost}</span>

                    </div>

                  ))}

                </div>

              </div>



            </div>



            {/* Right Column: Details & Recommendations */}

            <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">

              

              {/* Actionable Recommendations */}

              <div className="border border-emerald-900/40 bg-emerald-950/20 rounded-xl overflow-hidden shadow-lg">

                <div className="px-6 py-4 border-b border-emerald-900/40 flex items-center justify-between bg-emerald-900/10">

                  <h2 className="text-sm font-medium text-emerald-400 flex items-center gap-2">

                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">

                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />

                    </svg>

                    Сгенерированный CLAUDE.md

                  </h2>

                </div>

                <div className="p-6">

                  <p className="text-xs text-zinc-400 mb-5 leading-relaxed">

                    На основе анализа сформированы правила. Скачайте файл и положите в корень проекта.

                  </p>

                  <pre className="text-[11px] font-mono text-zinc-300 bg-zinc-950 p-4 rounded-lg border border-zinc-800/80 whitespace-pre-wrap leading-relaxed shadow-inner mb-5">

                    {sessionData?.artifactText || "Рекомендации не найдены"}

                  </pre>

                  

                  <div className="flex gap-3">

                    <button 

                      onClick={() => navigator.clipboard.writeText(sessionData?.artifactText || "")}

                      className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-xs font-medium rounded transition-colors border border-zinc-700"

                    >

                      Копировать

                    </button>

                    <button 

                      onClick={downloadArtifact}

                      className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded transition-colors shadow-md"

                    >

                      Скачать .md

                    </button>

                  </div>

                </div>

              </div>



              {/* Active Step Context */}

              <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl overflow-hidden min-h-[300px] shadow-sm flex-1">

                <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/80">

                  <h2 className="text-sm font-medium text-white">Инспектор шага</h2>

                </div>

                <div className="p-6">

                  {activeStep ? (

                    <div className="space-y-5">

                      <div>

                        <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">Событие</span>

                        <span className="text-sm text-zinc-200 font-medium">{activeStep.action}</span>

                        

                        {activeStep.classification && (

                          <div className="mt-3">

                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-zinc-800/80 text-amber-300/90 text-xs font-medium border border-zinc-700 shadow-sm">

                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">

                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />

                              </svg>

                              {activeStep.classification}

                            </span>

                          </div>

                        )}

                      </div>

                      

                      <div>

                        <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">Подробности (Raw Log)</span>

                        <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 text-xs font-mono text-zinc-400 leading-relaxed break-words shadow-inner overflow-y-auto max-h-48">

                          {activeStep.details}

                        </div>

                      </div>

                      

                      <div className="pt-5 border-t border-zinc-800/80">

                        <span className="block text-[10px] text-zinc-500 uppercase font-bold tracking-wider mb-1.5">Расход на шаге</span>

                        <p className="text-sm font-mono text-zinc-300">

                          {activeStep.cost} <span className="text-zinc-600 text-xs font-sans ml-2">({activeStep.type})</span>

                        </p>

                      </div>

                    </div>

                  ) : (

                    <div className="h-full flex flex-col items-center justify-center text-center pt-12 opacity-60">

                      <svg className="w-12 h-12 text-zinc-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">

                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />

                      </svg>

                      <span className="text-zinc-400 text-sm">Выберите шаг на таймлайне или в логе слева,<br/>чтобы посмотреть сырые данные и аналитику.</span>

                    </div>

                  )}

                </div>

              </div>



            </div>

          </div>

        ) : (

          /* Вкладка сравнения (хардкод-заглушка для красивой презентации) */

          <div className="border border-zinc-800 bg-zinc-900/30 rounded-xl p-8 shadow-sm">

            <h2 className="text-xl font-medium text-white mb-8">Эффективность применения правил</h2>

            

            <div className="grid grid-cols-2 gap-12">

              <div className="space-y-6">

                <h3 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">До (Без CLAUDE.md)</h3>

                <div className="p-6 bg-zinc-950 border border-zinc-800 rounded-xl space-y-4">

                  <div className="flex justify-between items-center">

                    <span className="text-zinc-400">Потрачено денег</span>

                    <span className="text-2xl font-mono text-white">$1.24</span>

                  </div>

                  <div className="flex justify-between items-center">

                    <span className="text-zinc-400">Зацикливаний</span>

                    <span className="text-2xl font-bold text-white">3</span>

                  </div>

                </div>

              </div>

              

              <div className="space-y-6">

                <h3 className="text-sm font-medium text-emerald-500 uppercase tracking-wider">После (С правилами)</h3>

                <div className="p-6 bg-emerald-950/20 border border-emerald-900/50 rounded-xl space-y-4 relative overflow-hidden">

                  <div className="absolute right-0 top-0 w-32 h-32 bg-emerald-500/10 blur-3xl rounded-full translate-x-10 -translate-y-10"></div>

                  <div className="flex justify-between items-center relative z-10">

                    <span className="text-zinc-300">Потрачено денег</span>

                    <div className="text-right">

                      <span className="text-2xl font-mono text-emerald-400 block">$0.85</span>

                      <span className="text-xs font-bold text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">↓ 31% экономия</span>

                    </div>

                  </div>

                  <div className="flex justify-between items-center relative z-10 mt-2">

                    <span className="text-zinc-300">Зацикливаний</span>

                    <div className="text-right">

                      <span className="text-2xl font-bold text-emerald

-400 block">0</span>

                      <span className="text-xs font-bold text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">Устранено</span>

                    </div>

                  </div>

                </div>

              </div>

            </div>

          </div>

        )}

      </main>

    </div>

  );

};



export default Dashboard;