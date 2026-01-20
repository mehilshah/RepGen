(function () {
    console.log("RepGen Extension Loaded");

    function injectButton() {
        if (document.getElementById("repgen-btn")) return;

        const sidebar = document.querySelector("#partial-discussion-sidebar") ||
            document.querySelector(".discussion-sidebar") ||
            document.querySelector(".layout-sidebar");
        if (!sidebar) {
            console.log("RepGen: Sidebar not found");
            return;
        }

        const container = document.createElement("div");
        container.className = "discussion-sidebar-item";

        const button = document.createElement("button");
        button.id = "repgen-btn";
        button.className = "btn btn-primary d-block width-full"; // GitHub classes
        button.innerText = "⚡ Reproduce with RepGen";
        button.style.marginTop = "10px";
        button.style.backgroundColor = "#8b5cf6"; // Purple
        button.style.borderColor = "#7c3aed";

        button.onclick = async () => {
            button.innerText = "⏳ Starting...";
            button.disabled = true;

            const bugReportUrl = window.location.href;
            // Guess repo url from current url
            // https://github.com/owner/repo/issues/123 -> https://github.com/owner/repo
            const repoUrl = window.location.href.split("/issues/")[0];

            try {
                const response = await fetch("http://localhost:8000/api/reproduce", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        bug_report: bugReportUrl,
                        repo_url: repoUrl
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    alert(`RepGen Task Started! ID: ${data.task_id}\nCheck the RepGen Dashboard for progress.`);
                    button.innerText = "✅ Started";
                } else {
                    button.innerText = "❌ Failed";
                    alert("Failed to start RepGen task. Is the server running?");
                }
            } catch (e) {
                console.error(e);
                button.innerText = "❌ Error";
                alert("Connection error. Ensure RepGen API is running at localhost:8000");
            }
        };

        container.appendChild(button);
        sidebar.prepend(container);
    }

    // Run on load and PJAX transitions
    injectButton();
    const observer = new MutationObserver(injectButton);
    observer.observe(document.body, { childList: true, subtree: true });

})();
