import React from "react";
import { ArrowRight, BookOpen } from "lucide-react";
import { Link } from "react-router-dom";

function OverviewPage() {
    return (
        <main className="hero-shell">
            <header className="hero-header">
                <div className="brand-row">
                    <BookOpen className="brand-icon" />
                    <div>
                        <h1 className="font-serif text-4xl text-slate-900">RepGen</h1>
                        <p className="brand-subtitle">Imitation Game: reproducing deep learning bugs with an intelligent agent</p>
                    </div>
                </div>
            </header>

            <section className="cta-card">
                <h2 className="cta-title">Overview</h2>
                <p className="cta-copy">
                    RepGen automates deep learning bug reproduction by combining retrieval, report restructuring, planning,
                    and iterative code generation with validation loops.
                </p>
                <p className="cta-copy">
                    Paper: <a className="paper-link" href="https://arxiv.org/html/2512.14990v3" target="_blank" rel="noreferrer">arXiv 2512.14990v3</a>
                </p>
                <Link to="/project" className="btn btn-secondary mt-6">
                    Explore Project Details
                    <ArrowRight size={16} />
                </Link>
            </section>

            <section className="hero-grid">
                <article className="info-card">
                    <h2 className="info-title">Problem</h2>
                    <p className="info-copy">
                        DL bugs are difficult to reproduce due to nondeterminism, dependencies, and sparse issue details.
                    </p>
                </article>
                <article className="info-card">
                    <h2 className="info-title">Approach</h2>
                    <p className="info-copy">
                        RepGen uses learning-enhanced context and a multi-stage generation pipeline guided by plans and feedback.
                    </p>
                </article>
                <article className="info-card">
                    <h2 className="info-title">Outcome</h2>
                    <p className="info-copy">
                        Reported results show strong effectiveness and reduced developer effort for bug reproduction tasks.
                    </p>
                </article>
            </section>
        </main>
    );
}

export default OverviewPage;
