import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
    Activity,
    CheckCircle,
    Clipboard,
    FileCode,
    FileText,
    Info,
    ListChecks,
    Loader,
    Play,
    Terminal,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "/~repgen/api/api";
const APPROX_PRICING = {
    openai: {
        "gpt-5.2": { input: 3.5, cached_input: 0.35, output: 28.0 },
        "gpt-5.1": { input: 2.5, cached_input: 0.25, output: 20.0 },
        "gpt-5": { input: 2.5, cached_input: 0.25, output: 20.0 },
        "gpt-5-mini": { input: 0.45, cached_input: 0.045, output: 3.6 },
        "gpt-4.1": { input: 3.5, cached_input: 0.875, output: 14.0 },
        "gpt-4o": { input: 4.25, cached_input: 2.125, output: 17.0 },
        "gpt-4o-mini": { input: 0.25, cached_input: 0.125, output: 1.0 },
        o1: { input: 15.0, cached_input: 7.5, output: 60.0 },
        o3: { input: 2.0, cached_input: 0.5, output: 8.0 },
        "o4-mini": { input: 1.1, cached_input: 0.275, output: 4.4 },
    },
    anthropic: {
        "claude-opus-4.6": { input: 5.0, cached_input: 0.5, output: 25.0 },
        "claude-sonnet-4.6": { input: 3.0, cached_input: 0.3, output: 15.0 },
        "claude-haiku-4.5": { input: 1.0, cached_input: 0.1, output: 5.0 },
    },
    google: {
        "gemini-2.5-pro": {
            tiers: {
                prompt_le_200k_tokens: { input: 1.25, output: 10.0, context_caching: 0.125 },
                prompt_gt_200k_tokens: { input: 2.5, output: 15.0, context_caching: 0.25 },
            },
        },
        "gemini-2.5-flash": { input: 0.3, output: 2.5, context_caching: 0.03 },
        "gemini-2.5-flash-lite": { input: 0.1, output: 0.4, context_caching: 0.01 },
    },
};

function basenamePath(pathLike) {
    if (!pathLike || typeof pathLike !== "string") return "unknown";
    const normalized = pathLike.replace(/\\/g, "/");
    return normalized.split("/").filter(Boolean).pop() || normalized;
}

function previewText(text, maxLines = 80) {
    if (!text || typeof text !== "string") return "";
    const lines = text.split("\n");
    if (lines.length <= maxLines) return text;
    return `${lines.slice(0, maxLines).join("\n")}\n...`;
}

function countLines(text) {
    if (!text || typeof text !== "string") return 0;
    return text.split("\n").length;
}

function estimateTokens(text) {
    if (!text || typeof text !== "string") return 0;
    return Math.max(1, Math.ceil(text.length / 4));
}

function parseStageLog(logLine) {
    const m = /^\[([^\]]+)\]\s*(.*)$/.exec(logLine || "");
    if (!m) return { stage: "info", message: logLine || "" };
    return { stage: (m[1] || "info").toLowerCase(), message: m[2] || "" };
}

function humanizeLogMessage(message) {
    if (!message) return "(No details)";
    let output = message.replace(/\s+/g, " ").trim();
    output = output
        .replace(/^Context\s+(\d+)\s+-\s+Attempt\s+(\d+)/i, "Context $1, Attempt $2")
        .replace(/^Plan Generated For Context\s+(\d+)/i, "Generated execution plan for context $1")
        .replace(/^Context\s+(\d+)\s+Loaded/i, "Loaded retrieval context $1")
        .replace(/^Bug Report Refined/i, "Refined bug report")
        .replace(/^Reproduction Successful/i, "Successfully generated a reproduction script");
    return output.charAt(0).toUpperCase() + output.slice(1);
}

function formatSectionHeading(heading) {
    if (!heading) return "";
    return heading
        .toLowerCase()
        .split(" ")
        .filter(Boolean)
        .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
        .join(" ");
}

function stageLabel(stage) {
    const labels = {
        setup: "Setup",
        retrieval: "Retrieval",
        refinement: "Refinement",
        generation: "Generation",
        info: "Info",
    };
    return labels[stage] || "Info";
}

function parsePlanArtifact(rawPlan) {
    if (!rawPlan) return { type: "empty", steps: [], raw: "" };
    const extractStepsFromArray = (arr) => arr
        .map((step, idx) => {
            if (typeof step === "string") {
                return {
                    idx: idx + 1,
                    title: step.trim() || `Step ${idx + 1}`,
                    description: "",
                    command: "",
                    expected: "",
                };
            }
            return {
                idx: idx + 1,
                title: step?.title || step?.step || step?.action || step?.name || `Step ${idx + 1}`,
                description: step?.description || step?.goal || step?.rationale || step?.details || "",
                command: step?.command || step?.cmd || "",
                expected: step?.expected || step?.validation || step?.output || "",
            };
        })
        .filter((step) => step.title || step.description || step.command || step.expected);

    const extractStepsFromText = (text) => {
        const lines = text.split("\n");
        const steps = [];
        let current = null;

        const stepStart = /^\s*(?:step\s*\d+[\s:.-]+|\d+[\).:-]\s+|[-*]\s+)(.+)$/i;
        for (const line of lines) {
            const m = stepStart.exec(line);
            if (m) {
                if (current) steps.push(current);
                current = m[1].trim();
                continue;
            }
            if (current && line.trim()) current += ` ${line.trim()}`;
        }
        if (current) steps.push(current);

        return steps.map((textStep, idx) => ({
            idx: idx + 1,
            title: textStep,
            description: "",
            command: "",
            expected: "",
        }));
    };

    try {
        const parsed = JSON.parse(rawPlan);
        let sourceSteps = [];
        if (Array.isArray(parsed)) sourceSteps = parsed;
        else if (Array.isArray(parsed?.steps)) sourceSteps = parsed.steps;
        else if (Array.isArray(parsed?.plan)) sourceSteps = parsed.plan;
        else if (Array.isArray(parsed?.reproduction_steps)) sourceSteps = parsed.reproduction_steps;
        else if (Array.isArray(parsed?.execution_steps)) sourceSteps = parsed.execution_steps;
        const steps = extractStepsFromArray(sourceSteps);
        if (steps.length > 0) return { type: "structured", steps, raw: rawPlan };
    } catch {
        // fall through to text parsing
    }

    const textSteps = extractStepsFromText(rawPlan);
    if (textSteps.length > 0) return { type: "structured", steps: textSteps, raw: rawPlan };
    return { type: "raw", steps: [], raw: rawPlan };
}

function parseRefinedReport(report) {
    const normalizeHeading = (line) => line
        .trim()
        .replace(/:$/, "")
        .replace(/\s+/g, " ")
        .toUpperCase();

    const headingMap = {
        "EXPECTED BEHAVIOR": "EXPECTED BEHAVIOUR",
    };
    const canonicalOrder = ["TITLE", "SYMPTOMS", "EXPECTED BEHAVIOUR", "REPRODUCTION STEPS"];

    const isAllCapsHeading = (line) => {
        const t = line.trim().replace(/:$/, "");
        if (!t || t.length > 80) return false;
        return /^[A-Z][A-Z0-9\s'()\-\/&]+$/.test(t);
    };

    const sections = {};
    let current = null;
    for (const rawLine of report.split("\n")) {
        const line = rawLine.trimEnd();
        const normalized = normalizeHeading(line);
        const heading = headingMap[normalized] || normalized;

        if (canonicalOrder.includes(heading) || isAllCapsHeading(line)) {
            current = heading;
            if (!sections[current]) sections[current] = [];
            continue;
        }
        if (current) sections[current].push(rawLine);
    }

    const orderedSections = [];
    canonicalOrder.forEach((h) => {
        if (sections[h]) {
            orderedSections.push({ heading: h, content: sections[h].join("\n").trim() });
            delete sections[h];
        }
    });
    Object.entries(sections).forEach(([heading, contentLines]) => {
        orderedSections.push({ heading, content: contentLines.join("\n").trim() });
    });

    return orderedSections.filter((section) => section.content);
}

function parseContextArtifact(rawContext) {
    if (!rawContext) return { ok: false, error: "No context available yet.", raw: "" };

    try {
        const parsed = JSON.parse(rawContext);
        const mainFilePath = parsed.main_file?.path || "";
        const mainFileName = basenamePath(mainFilePath);
        const mainContent = parsed.main_file?.content || "";
        const mainFileLines = typeof mainContent === "string" ? mainContent.split("\n").length : 0;
        const snippets = Array.isArray(parsed.module_snippets) ? parsed.module_snippets : [];
        const dependencies = Array.isArray(parsed.dependencies) ? parsed.dependencies : [];
        const canonicalSnippetLineKey = (snippet) => {
            const start = Number(snippet?.start_line || 0);
            const end = Number(snippet?.end_line || 0);
            if (start > 0 && end > 0) {
                const s = Math.min(start, end);
                const e = Math.max(start, end);
                return `${s}-${e}`;
            }
            const rawLines = String(snippet?.lines || "").trim().toLowerCase();
            if (!rawLines) return "n/a";
            // Normalize variants like "10 - 20", "L10-L20", "10–20" to the same key.
            const cleaned = rawLines
                .replace(/[–—]/g, "-")
                .replace(/\s+/g, "")
                .replace(/[^0-9,\-]/g, "");
            return cleaned || "n/a";
        };

        const dedupeSnippetsByLines = (entrySnippets) => {
            const seen = new Set();
            return entrySnippets.filter((snippet) => {
                const linesKey = canonicalSnippetLineKey(snippet);
                if (seen.has(linesKey)) return false;
                seen.add(linesKey);
                return true;
            });
        };

        const totalSnippetBlocks = snippets.reduce((count, entry) => {
            const entrySnippets = Array.isArray(entry?.snippets) ? dedupeSnippetsByLines(entry.snippets) : [];
            return count + entrySnippets.length;
        }, 0);
        const score = typeof parsed.score === "number" ? parsed.score : null;

        let confidence = "Baseline";
        if (score !== null) {
            if (score >= 0.7) confidence = "High";
            else if (score >= 0.45) confidence = "Medium";
            else confidence = "Low";
        }

        const summary = mainFilePath
            ? `Focused on ${mainFileName} with ${snippets.length} related file${snippets.length === 1 ? "" : "s"}.`
            : `Retrieved ${snippets.length} file${snippets.length === 1 ? "" : "s"} of relevant context.`;
        const reason = dependencies.length
            ? `Signals include ${dependencies.length} dependency reference${dependencies.length === 1 ? "" : "s"} and ${totalSnippetBlocks} code snippet${totalSnippetBlocks === 1 ? "" : "s"}.`
            : `Signals include ${totalSnippetBlocks} code snippet${totalSnippetBlocks === 1 ? "" : "s"} tied to the reported bug.`;

        const metrics = [
            { label: "Rank", value: parsed.rank ?? "N/A" },
            { label: "Score", value: score !== null ? score.toFixed(3) : "N/A" },
            { label: "Context files", value: snippets.length },
            { label: "Snippets", value: totalSnippetBlocks },
            { label: "Main file lines", value: mainFileLines || "N/A" },
        ];

        return {
            ok: true,
            confidence,
            confidenceScore: score,
            summary,
            reason,
            metrics,
            data: parsed,
            supportingFiles: snippets.map((entry) => {
                const uniqueSnippets = Array.isArray(entry.snippets) ? dedupeSnippetsByLines(entry.snippets) : [];
                return {
                    file: entry.file,
                    shortFile: basenamePath(entry.file),
                    snippetCount: uniqueSnippets.length,
                    snippets: uniqueSnippets.map((snippet, idx) => ({
                        id: `${entry.file}-${idx}`,
                        lines: snippet?.lines || "N/A",
                        code: previewText(snippet?.code || "", 18),
                    })),
                };
            }),
            raw: rawContext,
            mainContentPreview: previewText(mainContent, 100),
        };
    } catch {
        return { ok: false, error: "Context is not valid JSON. Showing raw output.", raw: rawContext };
    }
}

function providerFromBackend(backend) {
    if (backend === "claude") return "anthropic";
    if (backend === "gemini") return "google";
    return "openai";
}

function getModelPricing(backend, modelName, estimatedInputTokens) {
    if (!modelName) return null;
    const provider = providerFromBackend(backend);
    const catalog = APPROX_PRICING[provider] || {};
    const normalizedModel = String(modelName).trim().toLowerCase();

    const exactKey = Object.keys(catalog).find((key) => key.toLowerCase() === normalizedModel);
    const looseKey = Object.keys(catalog).find((key) => normalizedModel.includes(key.toLowerCase()) || key.toLowerCase().includes(normalizedModel));
    const matchedKey = exactKey || looseKey;
    if (!matchedKey) return null;

    const entry = catalog[matchedKey];
    if (entry?.tiers) {
        const tier = estimatedInputTokens <= 200_000 ? entry.tiers.prompt_le_200k_tokens : entry.tiers.prompt_gt_200k_tokens;
        return {
            inputPer1M: tier.input,
            outputPer1M: tier.output,
            cachedPer1M: tier.context_caching || null,
            label: `${provider}/${matchedKey} (${estimatedInputTokens <= 200_000 ? "<=200k tier" : ">200k tier"})`,
        };
    }

    return {
        inputPer1M: entry.input,
        outputPer1M: entry.output,
        cachedPer1M: entry.cached_input || entry.context_caching || null,
        label: `${provider}/${matchedKey}`,
    };
}

function estimateUsage({ logs, artifacts, bugReport, model, backend }) {
    const parsedLogs = logs.map(parseStageLog);
    const attempts = parsedLogs.filter((entry) => /^Context\s+\d+\s+-\s+Attempt\s+\d+$/i.test(entry.message)).length;
    const contexts = parsedLogs.filter((entry) => /Processing Context \d+\/\d+/i.test(entry.message)).length;
    const planCalls = parsedLogs.filter((entry) => /Plan Generated for Context/i.test(entry.message)).length;
    const refinementCalls = parsedLogs.filter((entry) => /Bug Report Refined/i.test(entry.message)).length || 1;

    const bugTokens = estimateTokens(bugReport);
    const refinedTokens = estimateTokens(artifacts?.refined_report || "");
    const contextTokens = estimateTokens(artifacts?.context || "");
    const planTokens = estimateTokens(artifacts?.plan || "");
    const codeTokens = estimateTokens(artifacts?.code || "");

    const inputPlan = (refinedTokens + contextTokens) * Math.max(planCalls, contexts, 1);
    const inputGenerate = (refinedTokens + contextTokens + planTokens) * Math.max(attempts, 1);
    const inputRefinement = bugTokens * Math.max(refinementCalls, 1);
    const relevanceChecks = Math.max(attempts - 1, 0);
    const inputRelevance = (refinedTokens + codeTokens) * relevanceChecks;

    const estimatedInputTokens = inputPlan + inputGenerate + inputRefinement + inputRelevance;
    const estimatedOutputTokens = (refinedTokens * Math.max(refinementCalls, 1)) + (planTokens * Math.max(planCalls, 1)) + codeTokens;
    const totalTokens = estimatedInputTokens + estimatedOutputTokens;

    const pricing = getModelPricing(backend, model, estimatedInputTokens);
    let estimatedCost = null;
    if (pricing) {
        estimatedCost = ((estimatedInputTokens / 1_000_000) * pricing.inputPer1M) +
            ((estimatedOutputTokens / 1_000_000) * pricing.outputPer1M);
    }

    return {
        estimatedInputTokens,
        estimatedOutputTokens,
        totalTokens,
        estimatedCost,
        pricing,
        attempts: Math.max(attempts, 1),
        contexts: Math.max(contexts, 1),
    };
}

function LogsPanel({ logs, artifacts, bugReport, model, backend }) {
    const parsedLogs = logs.map(parseStageLog);
    const grouped = parsedLogs.reduce((acc, entry) => {
        acc[entry.stage] = (acc[entry.stage] || 0) + 1;
        return acc;
    }, {});
    const latest = parsedLogs[parsedLogs.length - 1] || null;
    const stageOrder = ["setup", "retrieval", "refinement", "generation"];
    const completedStages = stageOrder.filter((stage) => grouped[stage]).length;
    const progressPercent = Math.round((completedStages / stageOrder.length) * 100);
    const usage = useMemo(
        () => estimateUsage({ logs, artifacts, bugReport, model, backend }),
        [logs, artifacts, bugReport, model, backend],
    );

    if (logs.length === 0) return <div className="placeholder-block">No logs yet...</div>;

    return (
        <div className="artifact-stack">
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Execution overview</h3>
                    <span className="artifact-meta">{logs.length} log entries</span>
                </div>
                <div className="progress-wrap mt-3">
                    <div className="progress-head">
                        <span>Pipeline progress</span>
                        <strong>{progressPercent}%</strong>
                    </div>
                    <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
                    </div>
                </div>
                <div className="artifact-chips">
                    {stageOrder.map((stage) => (
                        <span key={stage} className="artifact-chip">{stageLabel(stage)}: {grouped[stage] || 0}</span>
                    ))}
                </div>
                {latest && (
                    <div className="latest-log mt-3">
                        <span className={`log-stage log-stage-${latest.stage}`}>{stageLabel(latest.stage)}</span>
                        <p className="m-0">{humanizeLogMessage(latest.message)}</p>
                    </div>
                )}
            </div>
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Estimated Tokens & Cost</h3>
                    <span className="artifact-meta">Approximate</span>
                </div>
                <div className="artifact-chips">
                    <span className="artifact-chip">Model: {model || "N/A"}</span>
                    <span className="artifact-chip">Input tokens: {usage.estimatedInputTokens.toLocaleString()}</span>
                    <span className="artifact-chip">Output tokens: {usage.estimatedOutputTokens.toLocaleString()}</span>
                    <span className="artifact-chip">Total tokens: {usage.totalTokens.toLocaleString()}</span>
                    <span className="artifact-chip">Contexts: {usage.contexts}</span>
                    <span className="artifact-chip">Attempts: {usage.attempts}</span>
                </div>
                <div className="latest-log mt-3">
                    <span className="log-stage">Cost</span>
                    <p className="m-0">
                        {usage.estimatedCost !== null
                            ? `Estimated run cost: $${usage.estimatedCost.toFixed(4)} (${usage.pricing.label}, input $${usage.pricing.inputPer1M}/1M, output $${usage.pricing.outputPer1M}/1M${usage.pricing.cachedPer1M !== null ? `, cached input/context $${usage.pricing.cachedPer1M}/1M` : ""}).`
                            : "No pricing preset matched this model. Token estimate is shown, cost unavailable."}
                    </p>
                </div>
            </div>
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Execution timeline</h3>
                </div>
                <ol className="timeline-list">
                    {parsedLogs.map((entry, i) => (
                        <li key={`${entry.stage}-${i}`} className="timeline-item">
                            <div className="timeline-index">{i + 1}</div>
                            <div className="timeline-content">
                                <div className="timeline-head">
                                    <span className={`log-stage log-stage-${entry.stage}`}>{stageLabel(entry.stage)}</span>
                                </div>
                                <p className="timeline-message">{humanizeLogMessage(entry.message)}</p>
                            </div>
                        </li>
                    ))}
                </ol>
            </div>
        </div>
    );
}

function RefinedReportPanel({ report }) {
    const sections = useMemo(() => parseRefinedReport(report), [report]);

    return (
        <div className="artifact-stack">
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Refined report summary</h3>
                    <span className="artifact-meta">{countLines(report)} lines</span>
                </div>
                <div className="artifact-chips">
                    <span className="artifact-chip">{report.length} characters</span>
                    <span className="artifact-chip">{sections.length} sections</span>
                </div>
            </div>
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Structured report</h3>
                </div>
                {sections.length > 0 ? (
                    <div className="artifact-sections mt-3">
                        {sections.map((section, idx) => (
                            <article key={`${section.heading}-${idx}`} className="artifact-section-card">
                                <div className="artifact-section-title report-heading">{formatSectionHeading(section.heading)}</div>
                                <div className="report-text-block mt-2">{section.content}</div>
                            </article>
                        ))}
                    </div>
                ) : (
                    <div className="placeholder-block">Could not detect headings in refined report.</div>
                )}
                <details className="context-details mt-3">
                    <summary>Show raw refined report</summary>
                    <pre className="block-pre mt-3">{report}</pre>
                </details>
            </div>
        </div>
    );
}

function PlanPanel({ plan }) {
    const parsed = useMemo(() => parsePlanArtifact(plan), [plan]);

    if (parsed.type === "empty") return <div className="placeholder-block">Waiting for plan generation...</div>;

    return (
        <div className="artifact-stack">
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Execution plan</h3>
                    <span className="artifact-meta">
                        {parsed.type === "structured" ? `${parsed.steps.length} steps` : "Raw plan"}
                    </span>
                </div>
            </div>
            {parsed.type === "structured" && (
                <details className="context-details">
                    <summary>Step preview</summary>
                    <div className="artifact-sections mt-3">
                        {parsed.steps.map((step) => (
                            <article key={`plan-step-${step.idx}`} className="artifact-section-card plan-step-card">
                                <div className="plan-step-title">Step {step.idx}</div>
                                <p className="plan-step-copy">{step.title}</p>
                                {step.description && <p>{step.description}</p>}
                                {step.command && (
                                    <div className="mt-2">
                                        <div className="artifact-kv">Command</div>
                                        <pre className="block-pre mt-1">{step.command}</pre>
                                    </div>
                                )}
                                {step.expected && (
                                    <div className="mt-2">
                                        <div className="artifact-kv">Expected output</div>
                                        <p>{step.expected}</p>
                                    </div>
                                )}
                            </article>
                        ))}
                    </div>
                </details>
            )}
            <details className="context-details">
                <summary>Show raw plan</summary>
                <pre className="block-pre mt-3">{parsed.raw}</pre>
            </details>
        </div>
    );
}

function GeneratedCodePanel({ code, annotations, explanationLoading, explanationError }) {
    const [copied, setCopied] = useState(false);
    const [hoveredAnnotation, setHoveredAnnotation] = useState(null);
    const lines = useMemo(() => code.split("\n"), [code]);
    const coverage = useMemo(() => {
        const nonEmpty = lines
            .map((line, idx) => ({ line, no: idx + 1 }))
            .filter((item) => item.line.trim())
            .map((item) => item.no);
        if (nonEmpty.length === 0) {
            return { percent: 100, uncoveredRanges: [] };
        }

        const covered = new Set();
        (annotations || []).forEach((ann) => {
            const start = Number(ann?.start_line || 0);
            const end = Number(ann?.end_line || 0);
            if (!start || !end) return;
            const s = Math.min(start, end);
            const e = Math.max(start, end);
            for (let n = s; n <= e; n += 1) covered.add(n);
        });

        const uncovered = nonEmpty.filter((n) => !covered.has(n));
        const percent = Math.round(((nonEmpty.length - uncovered.length) / nonEmpty.length) * 100);

        const ranges = [];
        if (uncovered.length > 0) {
            let start = uncovered[0];
            let prev = uncovered[0];
            for (let i = 1; i < uncovered.length; i += 1) {
                const current = uncovered[i];
                if (current === prev + 1) {
                    prev = current;
                    continue;
                }
                ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
                start = current;
                prev = current;
            }
            ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
        }

        return { percent, uncoveredRanges: ranges };
    }, [lines, annotations]);

    const findAnnotationForLine = (lineNumber) => (
        (annotations || []).find((ann) => lineNumber >= ann.start_line && lineNumber <= ann.end_line) || null
    );

    const formatAnnotationLabel = (label) => (
        String(label || "")
            .trim()
            .replace(/[_-]+/g, " ")
            .toLowerCase()
            .split(/\s+/)
            .filter(Boolean)
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ")
    );

    const labelClass = (label) => {
        const level = likelihoodLevel(label);
        return `code-anno-likelihood-${level}`;
    };

    const likelihoodLevel = (label) => {
        const normalized = String(label || "").toLowerCase();
        if (normalized.includes("trigger") || normalized.includes("bug")) return 3;
        if (normalized.includes("error")) return 3;
        if (normalized.includes("train")) return 2;
        if (normalized.includes("model")) return 2;
        if (normalized.includes("weight")) return 2;
        if (normalized.includes("valid")) return 1;
        if (normalized.includes("eval")) return 1;
        if (normalized.includes("data")) return 1;
        return 2;
    };

    const isTriggerLabel = (label) => {
        const normalized = String(label || "").toLowerCase();
        return (
            normalized.includes("trigger")
            || normalized.includes("bug")
            || normalized.includes("failure")
            || normalized.includes("crash")
            || normalized.includes("exception")
            || normalized.includes("nan")
            || normalized.includes("symptom")
        );
    };

    const sidePopupText = (label) => {
        const level = likelihoodLevel(label);
        if (level === 3) return "Highly Likely To Have The Bug";
        if (level === 2) return "Moderately Likely To Have The Bug";
        return "Less Likely To Have A Bug";
    };

    const copyCode = async () => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            setCopied(false);
        }
    };

    return (
        <div className="artifact-stack">
            <div className="artifact-shell">
                <div className="artifact-header">
                    <h3>Generated reproduction code</h3>
                    <div className="code-header-meta">
                        <div className="code-header-stats">
                            <span className="artifact-meta">Explanation Coverage: {coverage.percent}%</span>
                            <span className="artifact-meta">{countLines(code)} lines</span>
                            <button type="button" className="btn btn-secondary text-xs" onClick={copyCode}>
                                <Clipboard size={14} />
                                {copied ? "Copied" : "Copy"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div className="code-explain-wrap">
                <div className="code-explain-panel">
                    <div className="code-explain-title">
                        <Info size={14} />
                        Segment explanation
                    </div>
                    {!explanationLoading && coverage.uncoveredRanges.length > 0 && !explanationError && (
                        <p>
                            Uncovered lines: {coverage.uncoveredRanges.join(", ")}
                        </p>
                    )}
                    {explanationLoading && <p>Generating line-level explanations...</p>}
                    {!explanationLoading && hoveredAnnotation && (
                        <p className="code-explain-copy">
                            <strong>{formatAnnotationLabel(hoveredAnnotation.label)}</strong>{" "}
                            (Lines {hoveredAnnotation.start_line}-{hoveredAnnotation.end_line}):{" "}
                            {hoveredAnnotation.explanation}
                        </p>
                    )}
                    {!explanationLoading && !hoveredAnnotation && !explanationError && (
                        <p>Hover over an annotated line block to view the explanation generated with the context.</p>
                    )}
                    {explanationError && <p>{explanationError}</p>}
                </div>
                <div className="block-pre code-block">
                    {lines.map((line, idx) => {
                        const lineNo = idx + 1;
                        const annotation = findAnnotationForLine(lineNo);
                        const activeRange = hoveredAnnotation
                            && lineNo >= hoveredAnnotation.start_line
                            && lineNo <= hoveredAnnotation.end_line;
                        const triggerPersistent = annotation && isTriggerLabel(annotation.label);
                        return (
                            <div
                                key={`line-${lineNo}`}
                                className={`code-line ${annotation ? `code-line-annotated ${labelClass(annotation.label)}` : ""
                                    } ${activeRange ? "code-line-active-range" : ""} ${triggerPersistent ? "code-line-trigger-persistent" : ""
                                    }`}
                                onMouseEnter={() => setHoveredAnnotation(annotation)}
                            >
                                <span className="code-line-no">{lineNo}</span>
                                <code className="code-line-text">{line || " "}</code>
                                {!explanationLoading
                                    && !explanationError
                                    && hoveredAnnotation
                                    && annotation
                                    && lineNo === hoveredAnnotation.start_line
                                    && (
                                        <div
                                            className={`code-risk-float code-risk-float-level-${likelihoodLevel(hoveredAnnotation.label)}`}
                                        >
                                            <div className="code-risk-float-title">
                                                {sidePopupText(hoveredAnnotation.label)}
                                            </div>
                                        </div>
                                    )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

function ContextPanel({ context, aiContextSummary, aiLoading, aiError }) {
    const parsed = useMemo(() => parseContextArtifact(context), [context]);
    const [showRaw, setShowRaw] = useState(false);

    if (!parsed.ok) {
        return (
            <div className="space-y-3">
                <div className="placeholder-block">{parsed.error}</div>
                {parsed.raw ? <pre className="block-pre max-h-[600px] overflow-auto">{parsed.raw}</pre> : null}
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="context-shell">
                <div className="context-header">
                    <div>
                        <div className="context-title">Context summary</div>
                        <p className="context-subtitle">{parsed.summary}</p>
                        <p className="context-subtitle">{parsed.reason}</p>
                        {parsed.confidenceScore !== null && (
                            <p className="context-subtitle">
                                Exact confidence score: <strong>{(parsed.confidenceScore * 100).toFixed(2)}%</strong>
                            </p>
                        )}
                    </div>
                    <span className="context-badge">{parsed.confidence} confidence</span>
                </div>

                <div className="context-metrics">
                    {parsed.metrics.map((metric) => (
                        <div key={metric.label} className="context-chip">
                            <span>{metric.label}</span>
                            <strong>{metric.value}</strong>
                        </div>
                    ))}
                </div>
            </div>

            <details className="context-details" open>
                <summary>
                    <ListChecks size={15} />
                    Why this context
                </summary>
                <ul className="context-list">
                    {parsed.supportingFiles.slice(0, 5).map((file) => (
                        <li key={`${file.file}-${file.snippetCount}`}>
                            <strong>{file.shortFile}</strong> - {file.snippetCount} snippet{file.snippetCount === 1 ? "" : "s"}
                        </li>
                    ))}
                    {parsed.supportingFiles.length > 5 && (
                        <li>+ {parsed.supportingFiles.length - 5} more supporting files</li>
                    )}
                </ul>
                <div className="ai-reason-card mt-3">
                    <div className="artifact-kv">AI explanation</div>
                    {aiLoading && <p className="mt-2 text-sm">Generating explanation...</p>}
                    {!aiLoading && Array.isArray(aiContextSummary) && aiContextSummary.length > 0 && (
                        <ul className="context-point-list">
                            {aiContextSummary.map((point, idx) => (
                                <li key={`ctx-point-${idx}`}>{point}</li>
                            ))}
                        </ul>
                    )}
                    {!aiLoading && (!aiContextSummary || aiContextSummary.length === 0) && !aiError && (
                        <p className="mt-2 text-sm">Context explanation will appear here.</p>
                    )}
                    {aiError && <p className="mt-2 text-sm">{aiError}</p>}
                </div>
            </details>

            {parsed.supportingFiles.some((file) => file.snippets.length > 0) && (
                <details className="context-details">
                    <summary>
                        <FileCode size={15} />
                        Snippet evidence
                    </summary>
                    <div className="snippet-grid">
                        {parsed.supportingFiles
                            .filter((file) => file.snippets.length > 0)
                            .slice(0, 4)
                            .map((file) => (
                                <article key={file.file} className="snippet-card">
                                    <div className="snippet-title">
                                        <strong>{file.shortFile}</strong>
                                        <span>{file.snippetCount} snippet{file.snippetCount === 1 ? "" : "s"}</span>
                                    </div>
                                    {file.snippets.slice(0, 2).map((snippet) => (
                                        <div key={snippet.id} className="mt-2">
                                            <div className="artifact-kv">Lines {snippet.lines}</div>
                                            <pre className="block-pre mt-1 max-h-[220px] overflow-auto">{snippet.code}</pre>
                                        </div>
                                    ))}
                                </article>
                            ))}
                    </div>
                </details>
            )}

            {Array.isArray(parsed.data.dependencies) && parsed.data.dependencies.length > 0 && (
                <details className="context-details">
                    <summary>
                        <Activity size={15} />
                        Dependencies
                    </summary>
                    <ul className="context-list">
                        {parsed.data.dependencies.slice(0, 8).map((dep, idx) => (
                            <li key={`${dep.module || "module"}-${dep.function || "function"}-${idx}`}>
                                <strong>{dep.module || "unknown"}</strong>
                                {dep.function ? `.${dep.function}` : ""}
                            </li>
                        ))}
                        {parsed.data.dependencies.length > 8 && (
                            <li>+ {parsed.data.dependencies.length - 8} more dependencies</li>
                        )}
                    </ul>
                </details>
            )}

            {parsed.mainContentPreview && (
                <details className="context-details">
                    <summary>
                        <FileText size={15} />
                        Main file preview
                    </summary>
                    <pre className="block-pre max-h-[500px] overflow-auto">{parsed.mainContentPreview}</pre>
                </details>
            )}

            <details className="context-details">
                <summary>
                    <Terminal size={15} />
                    Raw context
                </summary>
                <button type="button" className="btn btn-secondary text-xs" onClick={() => setShowRaw((prev) => !prev)}>
                    {showRaw ? "Hide raw JSON" : "Show raw JSON"}
                </button>
                {showRaw && <pre className="block-pre mt-3 max-h-[600px] overflow-auto">{parsed.raw}</pre>}
            </details>
        </div>
    );
}

function TryItPage() {
    const [bugReport, setBugReport] = useState("");
    const [backend, setBackend] = useState("");
    const [model, setModel] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [activeTab, setActiveTab] = useState("logs");
    const [artifacts, setArtifacts] = useState({});

    const [taskId, setTaskId] = useState(null);
    const [status, setStatus] = useState("idle");
    const [logs, setLogs] = useState([]);
    const [error, setError] = useState(null);
    const [aiContextInsights, setAiContextInsights] = useState({
        loading: false,
        error: "",
        contextReason: "",
        contextSummary: [],
        generatedForTaskId: null,
    });
    const [aiCodeInsights, setAiCodeInsights] = useState({
        loading: false,
        error: "",
        codeExplanation: "",
        codeAnnotations: [],
        generatedForTaskId: null,
    });

    const tabs = [
        { id: "logs", label: "Logs", icon: <Terminal size={16} /> },
        { id: "refined_report", label: "Refined Report", icon: <FileCode size={16} /> },
        { id: "plan", label: "Plan", icon: <Activity size={16} /> },
        { id: "context", label: "Context", icon: <CheckCircle size={16} /> },
        { id: "code", label: "Generated Code", icon: <CheckCircle size={16} /> },
    ];
    const activeTabMeta = tabs.find((tab) => tab.id === activeTab) || tabs[0];

    const startReproduction = async () => {
        if (!bugReport.trim() || !backend || !model.trim()) {
            setStatus("failed");
            setError("Bug report URL, backend, and model are required.");
            return;
        }

        try {
            setStatus("running");
            setTaskId(null);
            setLogs([]);
            setArtifacts({});
            setError(null);
            setAiContextInsights({
                loading: false,
                error: "",
                contextReason: "",
                contextSummary: [],
                generatedForTaskId: null,
            });
            setAiCodeInsights({
                loading: false,
                error: "",
                codeExplanation: "",
                codeAnnotations: [],
                generatedForTaskId: null,
            });
            setActiveTab("logs");

            const res = await axios.post(`${API_URL}/reproduce`, {
                bug_report: bugReport.trim(),
                backend,
                model: model.trim(),
                api_key: apiKey.trim() || null,
            });

            setTaskId(res.data.task_id);
        } catch (e) {
            setError(e.response?.data?.detail || e.message);
            setStatus("failed");
            setTaskId(null);
        }
    };

    useEffect(() => {
        let interval;
        if (taskId && status === "running") {
            interval = setInterval(async () => {
                try {
                    const res = await axios.get(`${API_URL}/status/${taskId}`);
                    const data = res.data;
                    setLogs(data.logs || []);
                    setArtifacts(data.artifacts || {});

                    if (data.status === "completed") {
                        setStatus("completed");
                        clearInterval(interval);
                        setActiveTab("code");
                    } else if (data.status === "failed") {
                        setStatus("failed");
                        setError(data.error);
                        clearInterval(interval);
                    }
                } catch (pollErr) {
                    console.error("Polling error", pollErr);
                }
            }, 2000);
        }

        return () => clearInterval(interval);
    }, [taskId, status]);

    const statusClass = {
        idle: "status-idle",
        running: "status-running",
        completed: "status-completed",
        failed: "status-failed",
    }[status] || "status-idle";

    const fetchContextInsights = async () => {
        if (!taskId) return;
        if (!artifacts.context) return;
        if (aiContextInsights.generatedForTaskId === taskId) {
            return;
        }
        if (aiContextInsights.loading) return;

        setAiContextInsights((prev) => ({ ...prev, loading: true, error: "" }));
        try {
            const response = await axios.post(`${API_URL}/explain/context`, {
                bug_report: bugReport.trim(),
                refined_report: artifacts.refined_report || "",
                context: artifacts.context || "",
                api_key: apiKey.trim() || null,
            });
            setAiContextInsights({
                loading: false,
                error: "",
                contextReason: response.data.context_reason || "",
                contextSummary: response.data.context_summary || [],
                generatedForTaskId: taskId,
            });
        } catch (explainErr) {
            setAiContextInsights((prev) => ({
                ...prev,
                loading: false,
                error: explainErr.response?.data?.detail || "Failed to generate context explanation.",
                generatedForTaskId: taskId,
            }));
        }
    };

    const fetchCodeInsights = async () => {
        if (!taskId) return;
        if (!artifacts.code) return;
        if (aiCodeInsights.generatedForTaskId === taskId) {
            return;
        }
        if (aiCodeInsights.loading) return;

        setAiCodeInsights((prev) => ({ ...prev, loading: true, error: "" }));
        try {
            const response = await axios.post(`${API_URL}/explain/code`, {
                bug_report: bugReport.trim(),
                refined_report: artifacts.refined_report || "",
                plan: artifacts.plan || "",
                code: artifacts.code || "",
                api_key: apiKey.trim() || null,
            });
            setAiCodeInsights({
                loading: false,
                error: "",
                codeExplanation: response.data.code_explanation || "",
                codeAnnotations: response.data.code_annotations || [],
                generatedForTaskId: taskId,
            });
        } catch (explainErr) {
            setAiCodeInsights((prev) => ({
                ...prev,
                loading: false,
                error: explainErr.response?.data?.detail || "Failed to generate code explanation.",
                generatedForTaskId: taskId,
            }));
        }
    };

    useEffect(() => {
        if (artifacts.context) {
            fetchContextInsights();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [taskId, artifacts.context]);

    useEffect(() => {
        if (artifacts.code) {
            fetchCodeInsights();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [taskId, artifacts.code]);

    return (
        <main className="content-shell">
            <section className="panel p-5 md:p-6 mt-4">
                <div className="section-head">
                    <h2 className="section-title">Run reproduction</h2>
                    <p className="section-copy">
                        Paste a GitHub issue URL. Repository is derived automatically from the issue.
                    </p>
                </div>
                <div className="form-grid">
                    <div className="field field-wide">
                        <label className="field-label">Bug Report URL</label>
                        <div className="input-shell">
                            <input
                                value={bugReport}
                                onChange={(e) => setBugReport(e.target.value)}
                                className="input-control"
                                placeholder="https://github.com/owner/repo/issues/123"
                            />
                        </div>
                    </div>

                    <div className="field">
                        <label className="field-label">Backend</label>
                        <div className="input-shell">
                            <select value={backend} onChange={(e) => setBackend(e.target.value)} className="select-control">
                                <option value="">Select backend</option>
                                <option value="openai">OpenAI</option>
                                <option value="claude">Claude</option>
                                <option value="gemini">Gemini</option>
                            </select>
                        </div>
                    </div>

                    <div className="field">
                        <label className="field-label">Model</label>
                        <div className="input-shell">
                            <input
                                value={model}
                                onChange={(e) => setModel(e.target.value)}
                                className="input-control"
                                placeholder="e.g. gpt-4o-mini"
                            />
                        </div>
                    </div>

                    <div className="field field-wide">
                        <label className="field-label">API Key (optional)</label>
                        <div className="input-shell">
                            <input
                                type="password"
                                value={apiKey}
                                onChange={(e) => setApiKey(e.target.value)}
                                className="input-control"
                                placeholder="sk-..."
                            />
                        </div>
                    </div>
                </div>

                <div className="mt-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="text-sm text-slate-600">
                        Using model <strong>{model || "N/A"}</strong> on <strong>{backend || "N/A"}</strong>
                    </div>
                    <button
                        onClick={startReproduction}
                        disabled={status === "running"}
                        className={`btn btn-primary md:min-w-[240px] ${status === "running" ? "btn-disabled" : ""}`}
                    >
                        {status === "running" ? <Loader className="animate-spin" /> : <Play />}
                        <span>{status === "running" ? "Reproducing..." : "Start Reproduction"}</span>
                    </button>
                </div>
            </section>

            <section className="workspace-card">
                <div className="tab-row">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`tab-btn ${activeTab === tab.id ? "tab-btn-active" : ""}`}
                        >
                            {tab.icon}
                            <span>{tab.label}</span>
                            {artifacts[tab.id] && <span className="ml-1 h-2 w-2 rounded-full bg-emerald-500"></span>}
                        </button>
                    ))}
                </div>

                <div className="p-6">
                    <div className="workspace-head">
                        <div>
                            <div className="workspace-title">{activeTabMeta.label}</div>
                            <div className="workspace-copy">Live output and generated artifacts for the current run.</div>
                        </div>
                        <div className="flex items-center gap-2">
                            {status === "failed" && error && <span className="error-text">({error})</span>}
                            <span className={`status-pill ${statusClass}`}>{status}</span>
                        </div>
                    </div>

                    {activeTab === "logs" && (
                        <LogsPanel logs={logs} artifacts={artifacts} bugReport={bugReport} model={model} backend={backend} />
                    )}

                    {activeTab === "refined_report" && (
                        artifacts.refined_report ? <RefinedReportPanel report={artifacts.refined_report} /> : <div className="placeholder-block">Waiting for report refinement...</div>
                    )}

                    {activeTab === "plan" && (
                        artifacts.plan ? <PlanPanel plan={artifacts.plan} /> : <div className="placeholder-block">Waiting for plan generation...</div>
                    )}

                    {activeTab === "context" && (
                        artifacts.context ? (
                            <ContextPanel
                                context={artifacts.context}
                                aiContextSummary={aiContextInsights.contextSummary}
                                aiLoading={aiContextInsights.loading}
                                aiError={aiContextInsights.error}
                            />
                        ) : <div className="placeholder-block">Waiting for context retrieval...</div>
                    )}

                    {activeTab === "code" && (
                        <div className="space-y-4">
                            {artifacts.code ? (
                                <GeneratedCodePanel
                                    code={artifacts.code}
                                    annotations={aiCodeInsights.codeAnnotations}
                                    explanationLoading={aiCodeInsights.loading}
                                    explanationError={aiCodeInsights.error}
                                />
                            ) : (
                                <div className="placeholder-block">Waiting for code generation...</div>
                            )}
                        </div>
                    )}
                </div>
            </section>
        </main>
    );
}

export default TryItPage;
