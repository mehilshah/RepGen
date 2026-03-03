import React from "react";
import {
    Activity,
    CheckCircle,
    Target,
    FlaskConical,
    Users,
    Timer,
    Brain,
    Layers,
    Wrench,
} from "lucide-react";

function InfoCard({ icon: Icon, title, children }) {
    return (
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                <Icon size={18} className="text-slate-700" />
                {title}
            </h2>
            <div className="mt-2 text-sm leading-6 text-slate-700">{children}</div>
        </article>
    );
}

function MetricCard({ value, label, icon: Icon }) {
    return (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <div className="text-3xl font-semibold text-slate-900">{value}</div>
                    <div className="mt-1 text-sm text-slate-600">{label}</div>
                </div>
                <div className="rounded-xl bg-slate-50 p-2 text-slate-700">
                    <Icon size={18} />
                </div>
            </div>
        </div>
    );
}

function Step({ n, title, copy }) {
    return (
        <div className="flex gap-4">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white">
                {n}
            </div>
            <div>
                <div className="text-base font-semibold text-slate-900">{title}</div>
                <div className="mt-1 text-sm leading-6 text-slate-700">{copy}</div>
            </div>
        </div>
    );
}

export default function ProjectPage() {
    return (
        <main className="mx-auto w-full max-w-6xl space-y-10 px-4 py-10 md:px-8">
            {/* Hero */}
            <section className="rounded-3xl border border-slate-200 bg-gradient-to-b from-white to-slate-50 p-6 shadow-sm md:p-10">
                <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-700">
                    <span className="font-medium">ICSE ’26</span>
                    <span className="text-slate-400">•</span>
                    <span>Deep Learning Bug Reproduction</span>
                </div>

                <h1 className="mt-4 font-serif text-3xl text-slate-900 md:text-4xl">
                    RepGen: Reproducing Deep Learning Bugs with an Intelligent Agent
                </h1>

                <p className="mt-3 max-w-3xl text-base leading-7 text-slate-700">
                    Deep learning (DL) bugs are hard to reproduce because training is nondeterministic and failures depend
                    on environment, frameworks, data pipelines, and hardware. RepGen is an automated, agentic workflow that
                    builds a learning-enhanced context from a project, generates a targeted reproduction plan, and then
                    iteratively generates code using a generate–validate–refine loop until the bug’s symptom is reproduced.
                </p>

                <div className="mt-5 flex flex-wrap gap-2">
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                        Learning-enhanced context
                    </span>
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                        Plan-driven reproduction
                    </span>
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                        Generate–validate–refine
                    </span>
                    <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white">
                        Silent-bug support
                    </span>
                </div>
            </section>

            {/* Top cards */}
            <section className="grid gap-4 md:grid-cols-3">
                <InfoCard icon={Target} title="Core Pipeline">
                    RepGen constructs task-relevant context from the project (training loop + dependencies), restructures the
                    bug report into an executable spec, generates a reproduction plan, and synthesizes runnable code with
                    feedback-guided refinement.
                </InfoCard>

                <InfoCard icon={Activity} title="Context Strategy">
                    Module-centric retrieval and training-loop extraction (AST-guided) help prioritize the most relevant code
                    and configuration. Ranking reduces noise so the agent operates on high-signal context.
                </InfoCard>

                <InfoCard icon={CheckCircle} title="Validation">
                    RepGen validates reproduction using standard signals (errors, static checks, relevance checks) and DL-aware
                    symptom checks that also cover “silent” failures like loss spikes or severe metric degradation.
                </InfoCard>
            </section>

            {/* Metrics */}
            <section className="space-y-4">
                <div className="flex items-end justify-between gap-4">
                    <h2 className="text-xl font-semibold text-slate-900">Key findings</h2>
                    <div className="text-sm text-slate-600">Empirical evaluation + developer study</div>
                </div>

                <div className="grid gap-4 md:grid-cols-4">
                    <MetricCard value="106" label="Real-world DL bugs evaluated" icon={FlaskConical} />
                    <MetricCard value="80.19%" label="Bug reproduction rate" icon={CheckCircle} />
                    <MetricCard value="19.81%" label="Improvement over prior SOTA" icon={Target} />
                    <MetricCard value="56.8%" label="Reduction in reproduction time" icon={Timer} />
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                    <MetricCard value="16" label="GitHub projects covered" icon={Layers} />
                    <MetricCard value="27" label="Developer study participants" icon={Users} />
                    <MetricCard value="Lower" label="Reported cognitive load" icon={Brain} />
                </div>
            </section>

            {/* How it works */}
            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:p-10">
                <div className="grid gap-10 md:grid-cols-2 md:items-start">
                    <div>
                        <h2 className="text-xl font-semibold text-slate-900">How RepGen works</h2>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                            RepGen is designed for DL pipelines where failures can originate outside a single function or file.
                            The workflow explicitly models environment setup, training/inference execution, and fault symptoms.
                        </p>

                        <div className="mt-6 space-y-5">
                            <Step
                                n={1}
                                title="Construct learning-enhanced context"
                                copy="Identify and assemble the most relevant artifacts (training loop, model code, configs, dependencies) into a compact context package."
                            />
                            <Step
                                n={2}
                                title="Restructure the bug report into an executable spec"
                                copy="Extract missing details and normalize the report into inputs, expected faulty symptom, constraints, and reproduction criteria."
                            />
                            <Step
                                n={3}
                                title="Generate a targeted reproduction plan"
                                copy="Plan environment and execution steps (setup, training/inference, checks), aligned with the bug’s reported symptom."
                            />
                            <Step
                                n={4}
                                title="Generate–validate–refine until reproduction"
                                copy="Iteratively generate runnable code and refine it using feedback from execution signals and DL-aware symptom validation."
                            />
                        </div>
                    </div>

                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">
                        <h3 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                            <Wrench size={18} className="text-slate-700" />
                            Why DL bug reproduction is different
                        </h3>
                        <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-700">
                            <li className="flex gap-2">
                                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-400" />
                                Nondeterminism: randomness in training can change whether a bug manifests.
                            </li>
                            <li className="flex gap-2">
                                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-400" />
                                Multi-artifact causes: bugs can span code, configs, data pipelines, and library/hardware versions.
                            </li>
                            <li className="flex gap-2">
                                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-400" />
                                Silent symptoms: many failures don’t crash—loss/metrics can be the primary signal.
                            </li>
                            <li className="flex gap-2">
                                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-400" />
                                Tight coupling: frameworks and accelerators influence correctness and reproducibility.
                            </li>
                        </ul>
                    </div>
                </div>
            </section>

            {/* Compact contributions */}
            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:p-10">
                <h2 className="text-xl font-semibold text-slate-900">Contributions</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-semibold text-slate-900">Technique</div>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                            A unified agentic workflow for DL bug reproduction that integrates context construction, plan generation,
                            and feedback-driven code synthesis.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-semibold text-slate-900">Evaluation</div>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                            Empirical evaluation on 106 real-world bugs and a controlled developer study (27 participants), reporting
                            improvements in success rate, time, and cognitive load.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-semibold text-slate-900">Benchmark</div>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                            A curated dataset of bug reports and artifacts spanning 16 deep learning projects to support future research.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                        <div className="text-sm font-semibold text-slate-900">Reproducibility</div>
                        <p className="mt-2 text-sm leading-6 text-slate-700">
                            A replication package enabling independent verification and follow-on work (implementation, dataset, results).
                        </p>
                    </div>
                </div>
            </section>
        </main>
    );
}