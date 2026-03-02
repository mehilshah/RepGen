import React from "react";
import { Activity, CheckCircle, Target } from "lucide-react";

function ProjectPage() {
    return (
        <main className="content-shell space-y-8">
            <section className="panel p-6 md:p-8">
                <h1 className="font-serif text-3xl text-slate-900">Project</h1>
                <p className="mt-3 text-base text-slate-700">
                    RepGen focuses on practical reproduction of deep learning bugs through learning-enhanced context construction,
                    structured planning, and iterative code generation.
                </p>
            </section>

            <section className="hero-grid">
                <article className="info-card">
                    <h2 className="info-title"><Target size={16} className="inline mr-2" />Core Pipeline</h2>
                    <p className="info-copy">
                        Build context from retrieved snippets and dependencies, restructure bug reports, generate reproducible plans,
                        and synthesize code with validation-guided refinement.
                    </p>
                </article>
                <article className="info-card">
                    <h2 className="info-title"><Activity size={16} className="inline mr-2" />Context Strategy</h2>
                    <p className="info-copy">
                        Module-centric retrieval, AST-driven training loop extraction, and cross-encoder ranking provide focused
                        context for LLM-based generation.
                    </p>
                </article>
                <article className="info-card">
                    <h2 className="info-title"><CheckCircle size={16} className="inline mr-2" />Reported Results</h2>
                    <p className="info-copy">
                        106 real-world DL bugs, 80.19% reproduction rate, 19.81% improvement over prior SOTA, and notable gains in
                        developer success, time, and cognitive load.
                    </p>
                </article>
            </section>

            <section className="panel p-6 md:p-8">
                <h2 className="info-title">Key Findings</h2>
                <div className="project-metrics">
                    <div className="metric-card">
                        <div className="metric-value">106</div>
                        <div className="metric-label">Real-world DL bugs evaluated</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">80.19%</div>
                        <div className="metric-label">Bug reproduction rate</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">19.81%</div>
                        <div className="metric-label">Improvement over prior SOTA</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">56.8%</div>
                        <div className="metric-label">Reduction in reproduction time</div>
                    </div>
                </div>
            </section>
        </main>
    );
}

export default ProjectPage;
