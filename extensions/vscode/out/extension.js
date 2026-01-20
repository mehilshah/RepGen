"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const API_URL = "http://localhost:8000/api";
const SidebarProvider_1 = require("./SidebarProvider");
function activate(context) {
    const sidebarProvider = new SidebarProvider_1.SidebarProvider(context.extensionUri);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider("repgen-sidebar", sidebarProvider));
    let disposable = vscode.commands.registerCommand('repgen.reproduce', async () => {
        // Fallback or specific command logic if needed,
        // but primarily we use the Sidebar now.
        vscode.commands.executeCommand('repgen-sidebar.focus');
    });
    context.subscriptions.push(disposable);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map