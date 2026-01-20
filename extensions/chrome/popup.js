document.addEventListener('DOMContentLoaded', async () => {
    const statusDiv = document.getElementById('status');
    const titleDiv = document.getElementById('title');
    const actionDiv = document.getElementById('action');
    const formDiv = document.getElementById('form');
    const startBtn = document.getElementById('startBtn');
    const apiKeyInput = document.getElementById('apiKey');
    const modelInput = document.getElementById('model');
    const resultDiv = document.getElementById('result');
    const dashboardBtnPlaceholder = document.getElementById('action');

    // Initial status
    statusDiv.textContent = "Initializing...";

    try {
        // Run queries concurrently for speed
        const [tabs, storageResult] = await Promise.all([
            chrome.tabs.query({ active: true, currentWindow: true }),
            chrome.storage.local.get(['currentTask'])
        ]);

        const tab = tabs[0];

        // Helpers
        const displayResult = (code) => {
            resultDiv.innerHTML = "";
            actionDiv.innerHTML = "";

            const codeBlock = document.createElement("textarea");
            codeBlock.value = code;
            codeBlock.style.width = "100%";
            codeBlock.style.height = "300px";
            codeBlock.style.fontFamily = "monospace";
            codeBlock.style.fontSize = "12px";
            codeBlock.readOnly = true;

            const copyBtn = document.createElement("button");
            copyBtn.innerText = "Copy Code";
            copyBtn.style.marginTop = "10px";
            copyBtn.onclick = () => {
                codeBlock.select();
                document.execCommand("copy");
                copyBtn.innerText = "Copied!";
                setTimeout(() => copyBtn.innerText = "Copy Code", 2000);
            };

            const clearBtn = document.createElement("button");
            clearBtn.innerText = "Start New";
            clearBtn.style.marginTop = "10px";
            clearBtn.style.marginLeft = "10px";
            clearBtn.onclick = async () => {
                await chrome.storage.local.remove(['currentTask']);
                location.reload();
            };

            resultDiv.appendChild(codeBlock);
            resultDiv.appendChild(copyBtn);
            resultDiv.appendChild(clearBtn);
        };

        const pollTask = (taskId) => {
            const interval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`http://localhost:8000/api/status/${taskId}`);
                    const statusData = await statusRes.json();

                    if (statusData.status === "completed") {
                        clearInterval(interval);
                        statusDiv.textContent = "Completed";

                        let code = "";
                        if (statusData.artifacts && statusData.artifacts.code) {
                            code = statusData.artifacts.code;
                        } else if (statusData.result && statusData.result.length > 0) {
                            code = statusData.result[0].content;
                        }

                        await chrome.storage.local.set({
                            currentTask: { taskId: taskId, status: 'completed', code: code }
                        });

                        displayResult(code);

                    } else if (statusData.status === "failed") {
                        clearInterval(interval);
                        statusDiv.textContent = "Failed";
                        resultDiv.innerHTML = `<p style="color:red">${statusData.error}</p>`;
                        startBtn.disabled = false;
                        startBtn.textContent = "Retry";
                        formDiv.style.display = "block";
                        await chrome.storage.local.remove(['currentTask']);
                    } else {
                        if (statusData.logs && statusData.logs.length > 0) {
                            const lastLog = statusData.logs[statusData.logs.length - 1];
                            resultDiv.innerHTML = `<p>Task ID: ${taskId}</p><p style="color:#666; font-size:10px">${lastLog}</p>`;
                        }
                    }
                } catch (err) {
                    console.error("Polling error", err);
                }
            }, 2000);
        };

        const restoreUI = (taskState) => {
            if (taskState.status === "running") {
                startBtn.disabled = true;
                startBtn.textContent = "Running...";
                statusDiv.textContent = "Running";
                formDiv.style.display = "none";
                resultDiv.innerHTML = `<p>Task ID: ${taskState.taskId}</p><p>Please wait...</p>`;
                pollTask(taskState.taskId);
                return true;
            } else if (taskState.status === "completed") {
                statusDiv.textContent = "Completed";
                formDiv.style.display = "none";
                displayResult(taskState.code);
                return true;
            }
            return false;
        };

        // 1. Try restoring state
        if (storageResult && storageResult.currentTask) {
            const restored = restoreUI(storageResult.currentTask);
            if (restored) return;
            // If failed to restore, fall through
            console.log("Invalid state, clearing");
            await chrome.storage.local.remove(['currentTask']);
        }

        // 2. Main Logic
        if (tab && tab.url && tab.url.includes("github.com") && tab.url.includes("/issues/")) {
            statusDiv.textContent = "Issue Detected";
            statusDiv.style.color = "green";
            titleDiv.textContent = tab.title.split("·")[0].trim();
            formDiv.style.display = "block";

            startBtn.onclick = async () => {
                const apiKey = apiKeyInput.value;
                const model = modelInput.value;

                if (!apiKey) {
                    resultDiv.textContent = "Please enter an API Key";
                    resultDiv.style.color = "red";
                    return;
                }

                startBtn.disabled = true;
                startBtn.textContent = "Starting...";
                resultDiv.textContent = "";

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

                        restoreUI({ taskId: taskId, status: 'running' });

                    } else {
                        const errText = await response.text();
                        startBtn.textContent = "Failed";
                        startBtn.disabled = false;
                        resultDiv.textContent = "Error: " + errText;
                        resultDiv.style.color = "red";
                    }
                } catch (e) {
                    startBtn.textContent = "Error";
                    startBtn.disabled = false;
                    resultDiv.textContent = "Connection failed. Is backend running?";
                    resultDiv.style.color = "red";
                }
            };

        } else {
            statusDiv.textContent = "Waiting...";
            titleDiv.textContent = "Navigate to a GitHub Issue";
            actionDiv.innerHTML = "<p>Go to a GitHub Issue page to use RepGen.</p>";
        }

    } catch (e) {
        console.error(e);
        statusDiv.textContent = "Error";
        statusDiv.style.color = "red";
        resultDiv.textContent = "Init Error: " + (e.message || e);
    }
});
