# Testing RepGen Ecosystem

This guide explains how to manually verify each component of the RepGen ecosystem.

## 1. 🔌 Verifying the API Server

The API is the core of the ecosystem. It must be running for the UI and Extensions to work.

### Steps
1. **Start the Server**:
   ```bash
   uvicorn repgen.server:app --reload
   ```
2. **Check Health**:
   Open http://localhost:8000/docs in your browser. You should see the Swagger UI.

3. **Test Endpoint** (Optional):
   You can trigger a dry-run task via `curl` (requires a valid repo/bug report, but you can just check if it accepts the request):
   ```bash
   curl -X POST "http://localhost:8000/api/reproduce" \
     -H "Content-Type: application/json" \
     -d '{
       "bug_report": "https://github.com/example/repo/issues/1",
       "repo_url": "https://github.com/example/repo",
       "backend": "openai",
       "model": "gpt-4o"
     }'
   ```
   You should receive a JSON response with a `"task_id"`.

---

## 2. 🖥️ Verifying the Web UI

The Web UI allows you to start and monitor tasks visually.

### Steps
1. **Ensure API is running** (see above).
2. **Setup UI**:
   ```bash
   cd ui
   npm install
   ```
3. **Start Dev Server**:
   ```bash
   npm run dev
   ```
4. **Test Flow**:
   - Open http://localhost:5173.
   - Enter a Bug Report URL and Repo URL.
   - Click **Start Reproduction**.
   - Verify that the status changes to "Running" and logs appear in the console window.

---

## 3. 🧩 Verifying Chrome Extension

This extension injects a button into GitHub pages.

### Steps
1. **Load Extension**:
   - Open Chrome and go to `chrome://extensions`.
   - Toggle **Developer Mode** (top right).
   - Click **Load unpacked**.
   - Select the `extensions/chrome` directory from this project.
2. **Test Injection**:
   - Navigate to any GitHub Issue page (e.g., `https://github.com/facebook/react/issues/123`).
   - Look at the **sidebar** on the right.
   - You should see a purple button: **"⚡ Reproduce with RepGen"**.
3. **Test Action**:
   - Click the button.
   - It should alert you with a Task ID (ensure API is running!).

---

## 4. 📝 Verifying VS Code Extension

This extension allows running RepGen from within VS Code.

### Steps
1. **Open Extension Project**:
   - Open the `extensions/vscode` folder in a new VS Code window.
2. **Install Dependencies**:
   ```bash
   npm install
   ```
3. **Debug**:
   - Press `F5` to open a new "Extension Development Host" window.
4. **Trigger Command**:
   - In the new window, press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows).
   - Type `RepGen: Reproduce Bug`.
   - Enter the requested URLs.
   - Verify that a progress notification appears in the status bar.

---

## 5. 🐳 Verifying Docker

Run the entire stack in a container.

### Steps
1. **Build Image**:
   ```bash
   docker build -t repgen .
   ```
2. **Run Container**:
   ```bash
   docker run -p 8000:8000 repgen
   ```
3. **Verify**:
   - Visit http://localhost:8000/docs to confirm the server is reachable from the host.
