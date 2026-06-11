const path = require("path");
const repoRoot = path.resolve(__dirname, "..");

module.exports = {
    apps: [
        {
            name: "repgen-server",
            script: "./run_server.sh",
            cwd: repoRoot,
            interpreter: "bash",
            watch: false,
            ignore_watch: ["temp_repos", "ui", "node_modules", ".git"],
        },
        {
            name: "repgen-ui",
            script: "npm",
            args: "run dev",
            cwd: __dirname,
            watch: false
        }
    ]
};
