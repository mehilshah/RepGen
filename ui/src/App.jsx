import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity, Terminal, Play, GitBranch, FileCode, CheckCircle, XCircle, Loader } from 'lucide-react';

const API_URL = "http://localhost:8000/api";

function App() {
    const [bugReport, setBugReport] = useState("");
    const [repoUrl, setRepoUrl] = useState("");
    const [backend, setBackend] = useState("openai");
    const [model, setModel] = useState("gpt-4o");
    const [apiKey, setApiKey] = useState("");

    const [taskId, setTaskId] = useState(null);
    const [status, setStatus] = useState("idle"); // idle, running, completed, failed
    const [logs, setLogs] = useState([]);
    const [result, setResult] = useState([]);
    const [error, setError] = useState(null);

    const startReproduction = async () => {
        try {
            setStatus("running");
            setLogs([]);
            setResult([]);
            setError(null);

            const res = await axios.post(`${API_URL}/reproduce`, {
                bug_report: bugReport,
                repo_url: repoUrl,
                backend: backend,
                model: model,
                api_key: apiKey
            });

            setTaskId(res.data.task_id);
        } catch (e) {
            setError(e.message);
            setStatus("failed");
        }
    };

    useEffect(() => {
        let interval;
        if (taskId && status === "running") {
            interval = setInterval(async () => {
                try {
                    const res = await axios.get(`${API_URL}/status/${taskId}`);
                    const data = res.data;
                    setLogs(data.logs || []);

                    if (data.status === "completed") {
                        setStatus("completed");
                        setResult(data.result || []);
                        clearInterval(interval);
                    } else if (data.status === "failed") {
                        setStatus("failed");
                        setError(data.error);
                        clearInterval(interval);
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 2000);
        }
        return () => clearInterval(interval);
    }, [taskId, status]);

    return (
        <div className="min-h-screen bg-gray-900 text-gray-100 p-8 font-mono">
            <div className="max-w-4xl mx-auto space-y-8">

                {/* Header */}
                <div className="flex items-center space-x-3 border-b border-gray-700 pb-4">
                    <Activity className="text-blue-500 w-8 h-8" />
                    <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">
                        RepGen
                    </h1>
                    <span className="text-gray-500 text-sm">Automated Bug Reproduction</span>
                </div>

                {/* Configuration Panel */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-4">
                        <label className="block text-sm font-medium text-gray-400">Bug Report URL / Path</label>
                        <div className="flex bg-gray-800 rounded-lg border border-gray-700 focus-within:border-blue-500 transition-colors">
                            <span className="p-3 text-gray-500"><Terminal size={18} /></span>
                            <input
                                value={bugReport}
                                onChange={(e) => setBugReport(e.target.value)}
                                className="bg-transparent w-full p-2 outline-none"
                                placeholder="https://github.com/user/repo/issues/123"
                            />
                        </div>
                    </div>

                    <div className="space-y-4">
                        <label className="block text-sm font-medium text-gray-400">Repository URL</label>
                        <div className="flex bg-gray-800 rounded-lg border border-gray-700 focus-within:border-blue-500 transition-colors">
                            <span className="p-3 text-gray-500"><GitBranch size={18} /></span>
                            <input
                                value={repoUrl}
                                onChange={(e) => setRepoUrl(e.target.value)}
                                className="bg-transparent w-full p-2 outline-none"
                                placeholder="https://github.com/user/repo"
                            />
                        </div>
                    </div>

                    <div className="space-y-4">
                        <label className="block text-sm font-medium text-gray-400">Backend</label>
                        <select
                            value={backend}
                            onChange={(e) => setBackend(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 outline-none"
                        >
                            <option value="openai">OpenAI</option>
                            <option value="ollama">Ollama</option>
                            <option value="claude">Claude</option>
                            <option value="gemini">Gemini</option>
                        </select>
                    </div>

                    <div className="space-y-4">
                        <label className="block text-sm font-medium text-gray-400">Model</label>
                        <input
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 outline-none"
                            placeholder="gpt-4o"
                        />
                    </div>

                    <div className="space-y-4 md:col-span-2">
                        <label className="block text-sm font-medium text-gray-400">API Key (Optional)</label>
                        <input
                            type="password"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 outline-none"
                            placeholder="sk-..."
                        />
                    </div>
                </div>

                {/* Action Button */}
                <button
                    onClick={startReproduction}
                    disabled={status === "running"}
                    className={`w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center space-x-2 transition-all transform active:scale-95
            ${status === "running" ? "bg-gray-700 cursor-not-allowed opacity-70" : "bg-gradient-to-r from-blue-600 to-purple-600 hover:shadow-lg hover:shadow-blue-500/20"}
          `}
                >
                    {status === "running" ? <Loader className="animate-spin" /> : <Play />}
                    <span>{status === "running" ? "Reproducing..." : "Start Reproduction"}</span>
                </button>

                {/* Status & Logs */}
                <div className="space-y-6">
                    <div className="flex justify-between items-center">
                        <h2 className="text-xl font-semibold">Live Logs</h2>
                        <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide
                ${status === "completed" ? "bg-green-500/20 text-green-400" :
                                status === "failed" ? "bg-red-500/20 text-red-400" :
                                    status === "running" ? "bg-blue-500/20 text-blue-400 animate-pulse" : "bg-gray-700 text-gray-400"}
              `}>
                            {status}
                        </span>
                    </div>

                    <div className="bg-black/50 rounded-xl p-4 h-64 overflow-y-auto border border-gray-800 font-mono text-sm space-y-1">
                        {logs.length === 0 && <span className="text-gray-600 italic">Waiting to start...</span>}
                        {logs.map((log, i) => (
                            <div key={i} className="text-gray-300 border-l-2 border-gray-700 pl-2">
                                {log}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Results */}
                {status === "completed" && (
                    <div className="bg-green-900/20 border border-green-800 rounded-xl p-6 space-y-4 animate-fade-in">
                        <div className="flex items-center space-x-3 text-green-400">
                            <CheckCircle />
                            <h3 className="text-lg font-bold">Reproduction Successful</h3>
                        </div>
                        <div className="space-y-2">
                            {result.map((file, i) => (
                                <div key={i} className="flex items-center space-x-2 bg-gray-900 p-3 rounded-lg">
                                    <FileCode className="text-purple-400" size={20} />
                                    <span className="text-gray-200">{file}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {status === "failed" && error && (
                    <div className="bg-red-900/20 border border-red-800 rounded-xl p-6 flex items-start space-x-3 animate-fade-in">
                        <XCircle className="text-red-500 mt-1" />
                        <div>
                            <h3 className="text-lg font-bold text-red-500">Reproduction Failed</h3>
                            <p className="text-gray-300 mt-1">{error}</p>
                        </div>
                    </div>
                )}

            </div>
        </div>
    )
}

export default App
