import React from "react";
import { ArrowRight, FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";

function OverviewPage() {
    return (
        <main className="mx-auto w-full max-w-6xl px-4 py-10 md:px-8">
            <section className="rounded-3xl border border-slate-200 bg-gradient-to-b from-white to-slate-50 p-6 shadow-sm md:p-10">
                <h1 className="font-serif text-4xl text-slate-900">RepGen</h1>
                <p className="mt-3 max-w-3xl text-base leading-7 text-slate-700">
                    An intelligent agent for practical deep learning bug reproduction—built for nondeterminism,
                    multi-artifact dependencies, and silent training failures.
                </p>

                <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
                    <Link to="/project" className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800">
                        Read the Project
                        <ArrowRight size={16} />
                    </Link>

                    <Link to="/try-it" className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-900 shadow-sm hover:bg-slate-50">
                        <FlaskConical size={16} />
                        Try RepGen
                    </Link>
                </div>
            </section>

            <section className="mt-8 grid gap-4 md:grid-cols-3">
                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h2 className="text-base font-semibold text-slate-900">Problem</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-700">
                        DL bugs are hard to reproduce because training is stochastic and failures depend on frameworks,
                        environments, and data pipelines.
                    </p>
                </article>

                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h2 className="text-base font-semibold text-slate-900">Approach</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-700">
                        RepGen builds project context, restructures reports into executable specs, plans targeted steps,
                        then iteratively generates and validates reproduction code.
                    </p>
                </article>

                <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h2 className="text-base font-semibold text-slate-900">Outcome</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-700">
                        Higher reproduction success and lower effort—especially for “silent” bugs that manifest as loss/metric issues.
                    </p>
                </article>
            </section>
        </main>
    );
}

export default OverviewPage;