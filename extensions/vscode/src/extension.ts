import * as vscode from 'vscode';
import axios from 'axios';

const API_URL = "http://localhost:8000/api";

export function activate(context: vscode.ExtensionContext) {

    let disposable = vscode.commands.registerCommand('repgen.reproduce', async () => {

        const bugReport = await vscode.window.showInputBox({
            prompt: "Enter Bug Report URL",
            placeHolder: "https://github.com/owner/repo/issues/1"
        });
        if (!bugReport) return;

        const repoUrl = await vscode.window.showInputBox({
            prompt: "Enter Repository URL",
            placeHolder: "https://github.com/owner/repo"
        });
        if (!repoUrl) return;

        // Start
        try {
            vscode.window.showInformationMessage(`Starting RepGen for ${bugReport}...`);

            const res = await axios.post(`${API_URL}/reproduce`, {
                bug_report: bugReport,
                repo_url: repoUrl
            });

            const taskId = res.data.task_id;

            // Poll
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "RepGen Reproducing...",
                cancellable: false
            }, async (progress) => {

                return new Promise<void>((resolve, reject) => {
                    const check = setInterval(async () => {
                        try {
                            const statusRes = await axios.get(`${API_URL}/status/${taskId}`);
                            const data = statusRes.data;

                            progress.report({ message: data.stage ? `[${data.stage}]` : "Working..." });

                            if (data.status === 'completed') {
                                clearInterval(check);
                                vscode.window.showInformationMessage(`RepGen Success! Files: ${data.result.join(', ')}`);
                                resolve();
                            } else if (data.status === 'failed') {
                                clearInterval(check);
                                vscode.window.showErrorMessage(`RepGen Failed: ${data.error}`);
                                resolve();
                            }
                        } catch (e) {
                            clearInterval(check);
                            vscode.window.showErrorMessage("Error polling RepGen API");
                            resolve();
                        }
                    }, 2000);
                });
            });

        } catch (e: any) {
            vscode.window.showErrorMessage(`Failed to start RepGen: ${e.message}`);
        }
    });

    context.subscriptions.push(disposable);
}

export function deactivate() { }
