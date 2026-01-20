import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Activity, Terminal, Play, GitBranch, FileCode, CheckCircle, XCircle, Loader } from 'lucide-react';

const API_URL = "http://localhost:8000/api";

function App() {
    const [bugReport, setBugReport] = useState("https://github.com/lucidrains/vit-pytorch/issues/347");
    const [repoUrl, setRepoUrl] = useState("https://github.com/lucidrains/vit-pytorch");
    const [backend, setBackend] = useState("openai");
    const [model, setModel] = useState("gpt-4o");
    const [apiKey, setApiKey] = useState("OPENAI_API_KEY");
    const [activeTab, setActiveTab] = useState("logs");
    const [artifacts, setArtifacts] = useState({});

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
            setArtifacts({});
            setError(null);
            setActiveTab("logs");

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
                    setArtifacts(data.artifacts || {});

                    if (data.status === "completed") {
                        setStatus("completed");
                        setResult(data.result || []);
                        clearInterval(interval);
                        setActiveTab("code"); // Switch to code on completion
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

    const tabs = [
        { id: "logs", label: "Logs", icon: <Terminal size={16} /> },
        { id: "refined_report", label: "Refined Report", icon: <FileCode size={16} /> },
        { id: "plan", label: "Plan", icon: <Activity size={16} /> },
        { id: "context", label: "Context", icon: <CheckCircle size={16} /> },
        { id: "code", label: "Generated Code", icon: <CheckCircle size={16} /> },
    ];

    return (
        <div className="min-h-screen bg-gray-900 text-gray-100 p-8 font-mono">
            <div className="max-w-6xl mx-auto space-y-8">

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

                {/* Main Content Area with Tabs */}
                <div className="bg-gray-800/50 rounded-xl border border-gray-700 overflow-hidden min-h-[500px] flex flex-col">
                    {/* Tab Navigation */}
                    <div className="flex border-b border-gray-700 overflow-x-auto">
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center space-x-2 px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap
                                    ${activeTab === tab.id
                                        ? "bg-gray-700 text-blue-400 border-b-2 border-blue-400"
                                        : "text-gray-400 hover:bg-gray-700/50 hover:text-gray-200"}`}
                            >
                                {tab.icon}
                                <span>{tab.label}</span>
                                {artifacts[tab.id] && <span className="w-2 h-2 rounded-full bg-green-500 ml-1"></span>}
                            </button>
                        ))}
                    </div>

                    {/* Tab Content */}
                    <div className="p-6 flex-1 overflow-y-auto">

                        {/* Status Banner */}
                        <div className="flex justify-between items-center mb-4">
                            <div className="flex items-center space-x-2">
                                <h2 className="text-xl font-semibold text-gray-200">
                                    {tabs.find(t => t.id === activeTab)?.label}
                                </h2>
                                {status === "failed" && error && <span className="text-red-400 text-sm">({error})</span>}
                            </div>

                            <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide
                                ${status === "completed" ? "bg-green-500/20 text-green-400" :
                                    status === "failed" ? "bg-red-500/20 text-red-400" :
                                        status === "running" ? "bg-blue-500/20 text-blue-400 animate-pulse" : "bg-gray-700 text-gray-400"}
                            `}>
                                {status}
                            </span>
                        </div>

                        {activeTab === "logs" && (
                            <div className="font-mono text-sm space-y-1">
                                {logs.length === 0 && <span className="text-gray-600 italic">No logs yet...</span>}
                                {logs.map((log, i) => (
                                    <div key={i} className="text-gray-300 border-l-2 border-gray-700 pl-2">
                                        {log}
                                    </div>
                                ))}
                            </div>
                        )}

                        {activeTab === "refined_report" && (
                            <div className="prose prose-invert max-w-none">
                                {artifacts.refined_report ? (
                                    <pre className="whitespace-pre-wrap text-sm text-gray-300 bg-black/30 p-4 rounded-lg">
                                        {artifacts.refined_report}
                                    </pre>
                                ) : (
                                    <div className="text-gray-500 italic flex items-center justify-center h-48">
                                        Waiting for report refinement...
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === "plan" && (
                            <div className="prose prose-invert max-w-none">
                                {artifacts.plan ? (
                                    <pre className="whitespace-pre-wrap text-sm text-blue-300 bg-blue-900/10 p-4 rounded-lg border border-blue-900/30">
                                        {artifacts.plan}
                                    </pre>
                                ) : (
                                    <div className="text-gray-500 italic flex items-center justify-center h-48">
                                        Waiting for plan generation...
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === "context" && (
                            <div className="prose prose-invert max-w-none">
                                {artifacts.context ? (
                                    <pre className="whitespace-pre-wrap text-sm text-gray-300 bg-black/30 p-4 rounded-lg max-h-[600px] overflow-auto">
                                        {artifacts.context}
                                    </pre>
                                ) : (
                                    <div className="text-gray-500 italic flex items-center justify-center h-48">
                                        Waiting for context retrieval...
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === "code" && (
                            <div className="space-y-4">
                                {artifacts.code ? (
                                    <>
                                        <div className="bg-green-900/20 border border-green-800 rounded-lg p-3 flex items-center space-x-2 text-green-400">
                                            <CheckCircle size={18} />
                                            <span className="font-mono text-sm">{artifacts.code_path}</span>
                                        </div>
                                        <pre className="whitespace-pre-wrap text-sm text-gray-200 bg-black/50 p-4 rounded-lg border border-gray-800 overflow-x-auto">
                                            {artifacts.code}
                                        </pre>
                                    </>
                                ) : (
                                    <div className="text-gray-500 italic flex items-center justify-center h-48">
                                        Waiting for code generation...
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    )
}

export default App
