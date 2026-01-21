import * as vscode from "vscode";
import axios from "axios";
import { getHtmlForWebview } from "./SidebarHtml";

const API_URL = "http://localhost:8000/api";

export class SidebarProvider implements vscode.WebviewViewProvider {
    _view?: vscode.WebviewView;

    constructor(private readonly _extensionUri: vscode.Uri) { }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
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
                        await vscode.window.withProgress(
                            {
                                location: vscode.ProgressLocation.Notification,
                                title: "RepGen: Starting Reproduction...",
                                cancellable: false,
                            },
                            async () => {
                                const res = await axios.post(`${API_URL}/reproduce`, {
                                    bug_report: bugReport, // eslint-disable-line @typescript-eslint/naming-convention
                                    repo_url: repoUrl, // eslint-disable-line @typescript-eslint/naming-convention
                                    api_key: apiKey, // eslint-disable-line @typescript-eslint/naming-convention
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
                            }
                        );
                    } catch (e: any) {
                        vscode.window.showErrorMessage(`RepGen Failed to Start: ${e.message}`);
                    }
                    break;
                }
                case "pollStatus": {
                    const taskId = data.value;
                    try {
                        const statusRes = await axios.get(`${API_URL}/status/${taskId}`);
                        const statusData = statusRes.data;
                        this._view?.webview.postMessage({
                            type: "statusUpdate",
                            value: statusData
                        });
                    } catch (e) {
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
                    } catch (e: any) {
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

    private _getHtmlForWebview(webview: vscode.Webview) {
        return getHtmlForWebview(webview);
    }
}
