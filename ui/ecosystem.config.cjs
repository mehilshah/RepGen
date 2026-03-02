module.exports = {
    apps: [
        {
            name: "repgen-server",
            script: "./run_server.sh",
            cwd: "../",
            interpreter: "bash",
            watch: false,
            ignore_watch: ["temp_repos", "ui", "node_modules", ".git"],
        },
        {
            name: "repgen-ui",
            script: "npm",
            args: "run dev",
            cwd: "./",
            watch: false
        }
    ]
};
