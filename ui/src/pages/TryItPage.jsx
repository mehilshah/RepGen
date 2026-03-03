import React, { useEffect, useState } from "react";
import axios from "axios";
import { Activity, CheckCircle, FileCode, GitBranch, Loader, Play, Terminal } from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "/~repgen/api/api";

function TryItPage() {
    const [bugReport, setBugReport] = useState("");
    const [repoUrl, setRepoUrl] = useState("");
    const [backend, setBackend] = useState("");
    const [model, setModel] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [activeTab, setActiveTab] = useState("logs");
    const [artifacts, setArtifacts] = useState({});

    const [taskId, setTaskId] = useState(null);
    const [status, setStatus] = useState("idle");
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);

    const tabs = [
        { id: "logs", label: "Logs", icon: <Terminal size={16} /> },
        { id: "refined_report", label: "Refined Report", icon: <FileCode size={16} /> },
        { id: "plan", label: "Plan", icon: <Activity size={16} /> },
        { id: "context", label: "Context", icon: <CheckCircle size={16} /> },
        { id: "code", label: "Generated Code", icon: <CheckCircle size={16} /> },
    ];

    const startReproduction = async () => {
        if (!bugReport.trim() || !repoUrl.trim() || !backend || !model.trim()) {
            setStatus("failed");
            setError("Bug report, repository, backend, and model are required.");
            return;
        }

        try {
            setStatus("running");
            setLogs([]);
            setArtifacts({});
            setError(null);
            setActiveTab("logs");

            const res = await axios.post(`${API_URL}/reproduce`, {
                bug_report: bugReport.trim(),
                repo_url: repoUrl.trim(),
                backend,
                model: model.trim(),
                api_key: apiKey.trim() || null,
            });

            setTaskId(res.data.task_id);
        } catch (e) {
            setError(e.response?.data?.detail || e.message);
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
                        clearInterval(interval);
                        setActiveTab("code");
                    } else if (data.status === "failed") {
                        setStatus("failed");
                        setError(data.error);
                        clearInterval(interval);
                    }
                } catch (pollErr) {
                    console.error("Polling error", pollErr);
                }
            }, 2000);
        }

        return () => clearInterval(interval);
    }, [taskId, status]);

    const statusClass = {
        idle: "status-idle",
        running: "status-running",
        completed: "status-completed",
        failed: "status-failed",
    }[status] || "status-idle";

    return (
        <main className="content-shell">

            <section className="panel p-5 md:p-6 mt-4">
                <div className="form-grid">
                    <div className="field">
                        <label className="field-label">Bug Report URL</label>
                        <div className="input-shell">
                            <input
                                value={bugReport}
                                onChange={(e) => setBugReport(e.target.value)}
                                className="input-control"
                                placeholder="https://github.com/owner/repo/issues/123"
                            />
                        </div>
                    </div>

                    <div className="field">
                        <label className="field-label">Repository URL</label>
                        <div className="input-shell">
                            <input
                                value={repoUrl}
                                onChange={(e) => setRepoUrl(e.target.value)}
                                className="input-control"
                                placeholder="https://github.com/owner/repo"
                            />
                        </div>
                    </div>

                    <div className="field">
                        <label className="field-label">Backend</label>
                        <div className="input-shell">
                            <select value={backend} onChange={(e) => setBackend(e.target.value)} className="select-control">
                                <option value="">Select backend</option>
                                <option value="openai">OpenAI</option>
                                <option value="claude">Claude</option>
                                <option value="gemini">Gemini</option>
                            </select>
                        </div>
                    </div>

                    <div className="field">
                        <label className="field-label">Model</label>
                        <div className="input-shell">
                            <input
                                value={model}
                                onChange={(e) => setModel(e.target.value)}
                                className="input-control"
                                placeholder="e.g. gpt-4o-mini"
                            />
                        </div>
                    </div>

                    <div className="field field-wide">
                        <label className="field-label">API Key (optional)</label>
                        <div className="input-shell">
                            <input
                                type="password"
                                value={apiKey}
                                onChange={(e) => setApiKey(e.target.value)}
                                className="input-control"
                                placeholder="sk-..."
                            />
                        </div>
                    </div>
                </div>

                <button
                    onClick={startReproduction}
                    disabled={status === "running"}
                    className={`btn btn-primary btn-wide mt-5 ${status === "running" ? "btn-disabled" : ""}`}
                >
                    {status === "running" ? <Loader className="animate-spin" /> : <Play />}
                    <span>{status === "running" ? "Reproducing..." : "Start Reproduction"}</span>
                </button>
            </section>

            <section className="workspace-card">
                <div className="tab-row">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`tab-btn ${activeTab === tab.id ? "tab-btn-active" : ""}`}
                        >
                            {tab.icon}
                            <span>{tab.label}</span>
                            {artifacts[tab.id] && <span className="ml-1 h-2 w-2 rounded-full bg-emerald-500"></span>}
                        </button>
                    ))}
                </div>

                <div className="p-6">
                    <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            {status === "failed" && error && <span className="error-text">({error})</span>}
                        </div>
                        <span className={`status-pill ${statusClass}`}>{status}</span>
                    </div>

                    {activeTab === "logs" && (
                        <div className="space-y-1 font-mono text-sm">
                            {logs.length === 0 && <span className="placeholder-block">No logs yet...</span>}
                            {logs.map((log, i) => (
                                <div key={i} className="log-row">{log}</div>
                            ))}
                        </div>
                    )}

                    {activeTab === "refined_report" && (
                        artifacts.refined_report ? <pre className="block-pre">{artifacts.refined_report}</pre> : <div className="placeholder-block">Waiting for report refinement...</div>
                    )}

                    {activeTab === "plan" && (
                        artifacts.plan ? <pre className="block-pre">{artifacts.plan}</pre> : <div className="placeholder-block">Waiting for plan generation...</div>
                    )}

                    {activeTab === "context" && (
                        artifacts.context ? <pre className="block-pre max-h-[600px] overflow-auto">{artifacts.context}</pre> : <div className="placeholder-block">Waiting for context retrieval...</div>
                    )}

                    {activeTab === "code" && (
                        <div className="space-y-4">
                            {artifacts.code ? (
                                <>
                                    <pre className="block-pre overflow-x-auto">{artifacts.code}</pre>
                                </>
                            ) : (
                                <div className="placeholder-block">Waiting for code generation...</div>
                            )}
                        </div>
                    )}
                </div>
            </section>
        </main>
    );
}

export default TryItPage;
