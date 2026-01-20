import * as vscode from 'vscode';
import axios from 'axios';

const API_URL = "http://localhost:8000/api";

import { SidebarProvider } from './SidebarProvider';

export function activate(context: vscode.ExtensionContext) {

    const sidebarProvider = new SidebarProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("repgen-sidebar", sidebarProvider)
    );

    let disposable = vscode.commands.registerCommand('repgen.reproduce', async () => {
        // Fallback or specific command logic if needed,
        // but primarily we use the Sidebar now.
        vscode.commands.executeCommand('repgen-sidebar.focus');
    });

    context.subscriptions.push(disposable);
}

export function deactivate() { }
