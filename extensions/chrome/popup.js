document.addEventListener('DOMContentLoaded', async () => {
    // UI Elements
    const statusBadge = document.getElementById('statusBadge');
    const issueCard = document.getElementById('issueCard');
    const issueTitle = document.getElementById('issueTitle');
    const emptyState = document.getElementById('emptyState');
    const setupForm = document.getElementById('setupForm');

    // Form Inputs
    const startBtn = document.getElementById('startBtn');
    const apiKeyInput = document.getElementById('apiKey');
    const modelInput = document.getElementById('model');
    const errorMsg = document.getElementById('errorMsg');

    // Result Area
    const resultArea = document.getElementById('resultArea');
    const codeOutput = document.getElementById('codeOutput');
    const progressLog = document.getElementById('progressLog');
    const actionButtons = document.getElementById('actionButtons');
    const copyBtn = document.getElementById('copyBtn');
    const resetBtn = document.getElementById('resetBtn');

    // Helpers
    const setStatus = (text, type = '') => {
        if (statusBadge) {
            statusBadge.textContent = text;
            statusBadge.className = 'status-badge ' + type;
        }
    };

    const showView = (viewName) => {
        // Simple view switcher
        if (emptyState) emptyState.classList.add('hidden');
        if (setupForm) setupForm.classList.add('hidden');
        if (resultArea) resultArea.classList.add('hidden');

        if (viewName === 'empty' && emptyState) emptyState.classList.remove('hidden');
        if (viewName === 'setup' && setupForm) setupForm.classList.remove('hidden');
        if (viewName === 'result' && resultArea) resultArea.classList.remove('hidden');
    };

    const displayResult = (code) => {
        showView('result');
        if (codeOutput) {
            codeOutput.value = code;
            codeOutput.classList.remove('hidden');
        }
        if (progressLog) progressLog.textContent = "Reproduction Complete";
        if (actionButtons) actionButtons.classList.remove('hidden');
        setStatus("Done", "success");
    };

    const displayRunning = (taskId) => {
        showView('result');
        if (codeOutput) codeOutput.classList.add('hidden');
        if (actionButtons) actionButtons.classList.add('hidden');
        if (progressLog) progressLog.textContent = "Detailed logs available in dashboard...";
        setStatus("Running", "running");

        // Start polling
        pollTask(taskId);
    };

    // --- State Logic ---

    // Clear Storage Helper
    if (resetBtn) {
        resetBtn.onclick = async () => {
            await chrome.storage.local.remove(['currentTask']);
            location.reload();
        };
    }

    if (copyBtn) {
        copyBtn.onclick = () => {
            if (codeOutput) {
                codeOutput.select();
                document.execCommand("copy");
                copyBtn.textContent = "Copied!";
                setTimeout(() => copyBtn.textContent = "Copy Code", 2000);
            }
        };
    }


    const pollTask = (taskId) => {
        const interval = setInterval(async () => {
            try {
                const statusRes = await fetch(`http://localhost:8000/api/status/${taskId}`);
                const statusData = await statusRes.json();

                if (statusData.status === "completed") {
                    clearInterval(interval);

                    let code = "";
                    if (statusData.artifacts && statusData.artifacts.code) {
                        code = statusData.artifacts.code;
                    } else if (statusData.result && statusData.result.length > 0) {
                        code = statusData.result[0].content;
                    }

                    // Save Completion State
                    await chrome.storage.local.set({
                        currentTask: { taskId: taskId, status: 'completed', code: code }
                    });

                    displayResult(code);

                } else if (statusData.status === "failed") {
                    clearInterval(interval);
                    setStatus("Failed", "error");
                    if (progressLog) progressLog.innerHTML = `<span style="color:var(--error)">${statusData.error}</span>`;

                    // Allow retry by showing reset button
                    if (actionButtons) actionButtons.classList.remove('hidden');
                    if (copyBtn) copyBtn.classList.add('hidden'); // Hide copy, show reset

                    await chrome.storage.local.remove(['currentTask']);
                } else {
                    // Update logs
                    if (statusData.logs && statusData.logs.length > 0) {
                        const lastLog = statusData.logs[statusData.logs.length - 1];
                        if (progressLog) progressLog.textContent = lastLog;
                    }
                }
            } catch (err) {
                console.error("Polling error", err);
            }
        }, 2000);
    };

    const restoreUI = (taskState) => {
        if (taskState.status === "running") {
            displayRunning(taskState.taskId);
            return true;
        } else if (taskState.status === "completed") {
            displayResult(taskState.code);
            return true;
        }
        return false;
    };

    // --- Initialization ---

    try {
        const [tabs, storageResult] = await Promise.all([
            chrome.tabs.query({ active: true, currentWindow: true }),
            chrome.storage.local.get(['currentTask'])
        ]);

        const tab = tabs[0];
        const isIssue = tab && tab.url && tab.url.includes("github.com") && tab.url.includes("/issues/");

        if (isIssue) {
            if (issueCard) issueCard.classList.remove('hidden');
            if (issueTitle) issueTitle.textContent = tab.title.split("·")[0].trim();
            setStatus("Ready", "active");
            showView('setup');
        } else {
            showView('empty');
            setStatus("Waiting");
        }

        // Try Restore
        if (storageResult && storageResult.currentTask) {
            const restored = restoreUI(storageResult.currentTask);
            if (!restored) await chrome.storage.local.remove(['currentTask']);
        }

        // Start Handler
        if (startBtn) {
            startBtn.onclick = async () => {
                const apiKey = apiKeyInput ? apiKeyInput.value : '';
                const model = modelInput ? modelInput.value : 'gpt-4o';
                if (errorMsg) errorMsg.textContent = "";

                if (!apiKey) {
                    if (errorMsg) errorMsg.textContent = "API Key is required";
                    return;
                }

                startBtn.disabled = true;
                startBtn.textContent = "Starting...";

                const bugReportUrl = tab.url;
                const repoUrl = tab.url.split("/issues/")[0];

                try {
                    const response = await fetch("http://localhost:8000/api/reproduce", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            bug_report: bugReportUrl,
                            repo_url: repoUrl,
                            api_key: apiKey,
                            model: model,
                            backend: "openai"
                        })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        const taskId = data.task_id;

                        await chrome.storage.local.set({
                            currentTask: { taskId: taskId, status: 'running' }
                        });

                        displayRunning(taskId);

                    } else {
                        const errText = await response.text();
                        startBtn.disabled = false;
                        startBtn.textContent = "Start Reproduction";
                        if (errorMsg) errorMsg.textContent = "Failed: " + errText;
                    }
                } catch (e) {
                    startBtn.disabled = false;
                    startBtn.textContent = "Start Reproduction";
                    if (errorMsg) errorMsg.textContent = "Connection Error. Is Backend Running?";
                }
            };
        }

    } catch (e) {
        console.error(e);
        document.body.innerHTML = `<div style="color:red; padding:20px">Init Error: ${e.message}</div>`;
    }
});
