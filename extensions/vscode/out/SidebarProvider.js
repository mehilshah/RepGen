"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SidebarProvider = void 0;
const vscode = require("vscode");
const axios_1 = require("axios");
const API_URL = "http://localhost:8000/api";
class SidebarProvider {
    constructor(_extensionUri) {
        this._extensionUri = _extensionUri;
    }
    resolveWebviewView(webviewView, context, _token) {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };
        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);
        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case "startReproduction": {
                    const { bugReport, repoUrl, apiKey, model } = data.value;
                    if (!apiKey) {
                        vscode.window.showErrorMessage("API Key is required");
                        return;
                    }
                    try {
                        vscode.window.withProgress({
                            location: vscode.ProgressLocation.Notification,
                            title: "RepGen: Starting Reproduction...",
                            cancellable: false,
                        }, async () => {
                            const res = await axios_1.default.post(`${API_URL}/reproduce`, {
                                bug_report: bugReport,
                                repo_url: repoUrl,
                                api_key: apiKey,
                                model: model,
                                backend: "openai",
                            });
                            if (res.data && res.data.task_id) {
                                this._view?.webview.postMessage({
                                    type: "taskStarted",
                                    value: res.data.task_id
                                });
                                vscode.window.showInformationMessage("RepGen Task Started!");
                            }
                        });
                    }
                    catch (e) {
                        vscode.window.showErrorMessage(`RepGen Failed to Start: ${e.message}`);
                    }
                    break;
                }
                case "pollStatus": {
                    const taskId = data.value;
                    try {
                        const statusRes = await axios_1.default.get(`${API_URL}/status/${taskId}`);
                        const statusData = statusRes.data;
                        this._view?.webview.postMessage({
                            type: "statusUpdate",
                            value: statusData
                        });
                    }
                    catch (e) {
                        console.error("Polling error", e);
                    }
                    break;
                }
                case "openInEditor": {
                    const code = data.value;
                    try {
                        const doc = await vscode.workspace.openTextDocument({
                            content: code,
                            language: "python"
                        });
                        await vscode.window.showTextDocument(doc);
                    }
                    catch (e) {
                        vscode.window.showErrorMessage(`Failed to open editor: ${e.message}`);
                    }
                    break;
                }
                case "onInfo": {
                    if (!data.value) {
                        return;
                    }
                    vscode.window.showInformationMessage(data.value);
                    break;
                }
                case "onError": {
                    if (!data.value) {
                        return;
                    }
                    vscode.window.showErrorMessage(data.value);
                    break;
                }
            }
        });
    }
    _getHtmlForWebview(webview) {
        const config = vscode.workspace.getConfiguration("repgen");
        const defaultKey = config.get("apiKey") || "";
        const defaultModel = config.get("model") || "gpt-4o";
        return `<!DOCTYPE html>
			<html lang="en">
			<head>
				<meta charset="UTF-8">
				<meta name="viewport" content="width=device-width, initial-scale=1.0">
				<title>RepGen</title>
                <style>
                    :root {
                        --container-padding: 20px;
                        --input-padding: 8px;
                        --button-padding: 10px;
                        --radius: 4px;
                    }
                    body { 
                        font-family: var(--vscode-font-family); 
                        padding: var(--container-padding); 
                        color: var(--vscode-foreground);
                        background-color: var(--vscode-editor-background);
                    }
                    h2 {
                        font-size: 14px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        margin-bottom: 20px;
                        color: var(--vscode-descriptionForeground);
                        border-bottom: 1px solid var(--vscode-widget-border);
                        padding-bottom: 5px;
                    }
                    .form-group { margin-bottom: 20px; }
                    label { 
                        display: block; 
                        margin-bottom: 8px; 
                        font-weight: 600; 
                        font-size: 12px;
                    }
                    input, select, textarea { 
                        width: 100%; 
                        padding: var(--input-padding); 
                        box-sizing: border-box; 
                        background: var(--vscode-input-background); 
                        color: var(--vscode-input-foreground); 
                        border: 1px solid var(--vscode-input-border); 
                        border-radius: var(--radius);
                        outline: none;
                    }
                    input:focus, select:focus, textarea:focus {
                        border-color: var(--vscode-focusBorder);
                    }
                    button {
                        width: 100%;
                        padding: var(--button-padding);
                        background: var(--vscode-button-background);
                        color: var(--vscode-button-foreground);
                        border: none;
                        border-radius: var(--radius);
                        cursor: pointer;
                        font-weight: 600;
                        transition: background 0.2s;
                    }
                    button:hover {
                        background: var(--vscode-button-hoverBackground);
                    }
                    button.secondary {
                        background: var(--vscode-button-secondaryBackground);
                        color: var(--vscode-button-secondaryForeground);
                        margin-top: 10px;
                    }
                    button.secondary:hover {
                         background: var(--vscode-button-secondaryHoverBackground);
                    }
                    .hidden { display: none !important; }
                    
                    /* Status & Logs */
                    .status-container {
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        height: 200px;
                        text-align: center;
                    }
                    .spinner {
                        border: 4px solid var(--vscode-widget-border);
                        border-top: 4px solid var(--vscode-progressBar-background);
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        animation: spin 1s linear infinite;
                        margin-bottom: 15px;
                    }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                    
                    #logs {
                        margin-top: 20px;
                        font-family: 'Courier New', Courier, monospace;
                        font-size: 11px;
                        color: var(--vscode-textPreformat-foreground);
                        opacity: 0.8;
                    }

                    /* Result View */
                    .code-preview {
                        background: var(--vscode-editor-inactiveSelectionBackground);
                        padding: 10px;
                        border-radius: var(--radius);
                        font-family: 'Courier New', monospace;
                        font-size: 12px;
                        max-height: 200px;
                        overflow-y: auto;
                        margin-bottom: 15px;
                        white-space: pre-wrap;
                        border: 1px solid var(--vscode-widget-border);
                    }
                    .success-icon {
                        color: var(--vscode-testing-iconPassed);
                        font-size: 40px;
                        margin-bottom: 10px;
                    }
                </style>
			</head>
			<body>
				<!-- Setup View -->
                <div id="setup-view">
                    <h2>Configuration</h2>
                    <div class="form-group">
                        <label>Bug Report URL</label>
                        <input type="text" id="bugReport" placeholder="https://github.com/owner/repo/issues/1" />
                    </div>
                     <div class="form-group">
                        <label>Repository URL</label>
                        <input type="text" id="repoUrl" placeholder="https://github.com/owner/repo" />
                    </div>
                     <div class="form-group">
                        <label>API Key</label>
                        <input type="password" id="apiKey" value="${defaultKey}" placeholder="sk-..." />
                    </div>
                     <div class="form-group">
                        <label>Model</label>
                        <input type="text" id="model" value="${defaultModel}" placeholder="gpt-4o" />
                    </div>
                    <button id="startBtn">Reproduce</button>
                </div>

                <!-- Running View -->
                <div id="running-view" class="hidden">
                    <div class="status-container">
                        <div class="spinner"></div>
                        <h3 id="statusHeading">Working...</h3>
                        <div id="logs">Initializing environment...</div>
                    </div>
                    <button id="cancelBtn" class="secondary">Cancel / Reset</button>
                </div>
                
                <!-- Result View -->
                <div id="result-view" class="hidden">
                     <div style="text-align:center; margin-bottom:20px;">
                        <div class="success-icon">✓</div>
                        <h3>Reproduction Complete</h3>
                     </div>
                     
                     <label>Generated Code:</label>
                     <div class="code-preview" id="codeDisplay">// Code will appear here...</div>
                     
                     <button id="openEditorBtn">Open in Editor</button>
                     <button id="resetBtn" class="secondary">Start New Task</button>
                </div>

                <script>
                    const vscode = acquireVsCodeApi();
                    
                    const startBtn = document.getElementById('startBtn');
                    const bugInput = document.getElementById('bugReport');
                    const repoInput = document.getElementById('repoUrl');
                    const keyInput = document.getElementById('apiKey');
                    const modelInput = document.getElementById('model');
                    const codeDisplay = document.getElementById('codeDisplay');
                    const statusHeading = document.getElementById('statusHeading');

                    const setupView = document.getElementById('setup-view');
                    const runningView = document.getElementById('running-view');
                    const resultView = document.getElementById('result-view');
                    const logs = document.getElementById('logs');
                    
                    let pollInterval = null;
                    let currentCode = "";

                    // Restore state
                     const previousState = vscode.getState();
                     if (previousState && previousState.taskId) {
                         showRunning(previousState.taskId);
                     } else if (previousState && previousState.code) {
                         showResult(previousState.code);
                     }

                    startBtn.addEventListener('click', () => {
                        const bug = bugInput.value;
                        const repo = repoInput.value;
                        const key = keyInput.value;
                        const model = modelInput.value;

                        if(!bug || !repo || !key) {
                             vscode.postMessage({ type: 'onError', value: 'Please fill in all fields' });
                             return;
                        }

                        vscode.postMessage({
                            type: 'startReproduction',
                            value: { bugReport: bug, repoUrl: repo, apiKey: key, model: model }
                        });
                    });
                    
                    document.getElementById('cancelBtn').addEventListener('click', reset);
                    document.getElementById('resetBtn').addEventListener('click', reset);
                    
                    document.getElementById('openEditorBtn').addEventListener('click', () => {
                        vscode.postMessage({ type: 'openInEditor', value: currentCode });
                    });

                    function reset() {
                        clearInterval(pollInterval);
                        vscode.setState(undefined);
                        setupView.classList.remove('hidden');
                        runningView.classList.add('hidden');
                        resultView.classList.add('hidden');
                        currentCode = "";
                    }

                    function showRunning(taskId) {
                        setupView.classList.add('hidden');
                        runningView.classList.remove('hidden');
                        resultView.classList.add('hidden');
                        
                         if (pollInterval) clearInterval(pollInterval);
                         pollInterval = setInterval(() => {
                            vscode.postMessage({ type: 'pollStatus', value: taskId });
                         }, 2000);
                    }
                    
                    function showResult(code) {
                        clearInterval(pollInterval);
                        currentCode = code;
                        codeDisplay.textContent = code.substring(0, 500) + (code.length > 500 ? "\\n... (Click Open in Editor)" : "");
                        
                        setupView.classList.add('hidden');
                        runningView.classList.add('hidden');
                        resultView.classList.remove('hidden');
                    }

                    window.addEventListener('message', event => {
                        const message = event.data;
                        switch (message.type) {
                            case 'taskStarted':
                                const taskId = message.value;
                                vscode.setState({ taskId: taskId });
                                showRunning(taskId);
                                break;
                            case 'statusUpdate':
                                const status = message.value;
                                if(logs) {
                                    if (status.logs && status.logs.length > 0) {
                                        logs.textContent = status.logs[status.logs.length - 1];
                                    } else if (status.stage) {
                                        logs.textContent = status.stage;
                                        statusHeading.textContent = status.stage;
                                    }
                                }
                                
                                if (status.status === 'completed') {
                                    let code = "";
                                    if (status.artifacts && status.artifacts.code) {
                                        code = status.artifacts.code;
                                    } else if (status.result && status.result.length > 0) {
                                        code = status.result[0].content;
                                    }
                                    
                                    vscode.setState({ code: code });
                                    showResult(code);
                                    
                                } else if (status.status === 'failed') {
                                    clearInterval(pollInterval);
                                    vscode.setState(undefined);
                                    runningView.classList.add('hidden');
                                    setupView.classList.remove('hidden');
                                    vscode.postMessage({ type: 'onError', value: 'RepGen Failed: ' + status.error });
                                }
                                break;
                        }
                    });

                </script>
			</body>
			</html>`;
    }
}
exports.SidebarProvider = SidebarProvider;
//# sourceMappingURL=SidebarProvider.js.map