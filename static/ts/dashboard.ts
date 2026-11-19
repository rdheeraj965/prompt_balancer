interface StoredMessage {
    role: "user" | "assistant";
    content: string;
    tierLabel?: string;
    modelName?: string;
    latency?: string;
    cost?: string;
    blocked?: boolean;
}

interface ChatSession {
    id: string;
    title: string;
    updatedAt: number;
    messages: StoredMessage[];
}

interface AttachedFile {
    name: string;
    content: string;
    estTokens: number;
}

document.addEventListener("DOMContentLoaded", () => {
    const STORAGE_KEY = "prompt_balancer_sessions_v1";

    const TIER_META: Record<string, { label: string; model: string; badgeClass: string }> = {
        CACHE: {
            label: "SEMANTIC CACHE",
            model: "Redis Vector Hit",
            badgeClass: "bg-teal-500/20 text-teal-300 border-teal-500/40",
        },
        TIER_1_LOCAL_LIGHT: {
            label: "TIER 1 • LOCAL",
            model: "gemma4:e2b",
            badgeClass: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
        },
        TIER_2_CLOUD_LIGHT: {
            label: "TIER 2 • CLOUD LITE",
            model: "gemini-3.5-flash-lite",
            badgeClass: "bg-sky-500/20 text-sky-300 border-sky-500/40",
        },
        TIER_3_CLOUD_HEAVY: {
            label: "TIER 3 • CLOUD HEAVY",
            model: "gemini-3.8-flash",
            badgeClass: "bg-purple-500/20 text-purple-300 border-purple-500/40",
        },
    };

    let sessions: ChatSession[] = loadSessions();
    let activeSessionId: string = crypto.randomUUID();
    let currentMessages: StoredMessage[] = [];
    let attachedFile: AttachedFile | null = null;
    let currentAbortController: AbortController | null = null;
    let isStreaming = false;
    let tierChartInstance: any = null;
    let latencyChartInstance: any = null;

    // DOM Elements
    const sendBtn = document.getElementById("send-btn") as HTMLButtonElement;
    const newChatBtn = document.getElementById("new-chat-btn") as HTMLButtonElement;
    const promptInput = document.getElementById("prompt-input") as HTMLTextAreaElement;
    const tierOverride = document.getElementById("tier-override") as HTMLSelectElement;
    const chatHistory = document.getElementById("chat-history") as HTMLDivElement;
    const savedChatsList = document.getElementById("saved-chats-list") as HTMLDivElement;
    const savedCount = document.getElementById("saved-count") as HTMLSpanElement;
    const chatSessionTitle = document.getElementById("chat-session-title") as HTMLSpanElement;

    const fileInput = document.getElementById("file-upload-input") as HTMLInputElement;
    const attachFileBtn = document.getElementById("attach-file-btn") as HTMLButtonElement;
    const fileChip = document.getElementById("file-chip") as HTMLDivElement;
    const fileChipLabel = document.getElementById("file-chip-label") as HTMLSpanElement;
    const removeFileBtn = document.getElementById("remove-file-btn") as HTMLButtonElement;

    const metricLatency = document.getElementById("metric-latency") as HTMLSpanElement;
    const metricCost = document.getElementById("metric-cost") as HTMLSpanElement;
    const eventBadge = document.getElementById("event-badge") as HTMLSpanElement;
    const securityBanner = document.getElementById("security-banner") as HTMLDivElement;
    const scoreComplexity = document.getElementById("score-complexity") as HTMLSpanElement;
    const scoreTokens = document.getElementById("score-tokens") as HTMLSpanElement;

    const hwBadge = document.getElementById("hw-health-badge") as HTMLSpanElement;
    const hwCpu = document.getElementById("hw-cpu") as HTMLSpanElement;
    const hwRam = document.getElementById("hw-ram") as HTMLSpanElement;
    const hwVram = document.getElementById("hw-vram") as HTMLSpanElement;
    const hwStatus = document.getElementById("hw-status") as HTMLSpanElement;

    const openAnalyticsBtn = document.getElementById("open-analytics-btn") as HTMLButtonElement;
    const closeAnalyticsBtn = document.getElementById("close-analytics-btn") as HTMLButtonElement;
    const resetAnalyticsBtn = document.getElementById("reset-analytics-btn") as HTMLButtonElement;
    const analyticsModal = document.getElementById("analytics-modal") as HTMLDivElement;

    // ---------------------------------------------------------
    // Markdown + KaTeX + Copy Code Button Renderer
    // ---------------------------------------------------------
    function renderFormattedContent(targetEl: HTMLElement, rawText: string): void {
        const w = window as any;
        if (!w.marked || !w.DOMPurify) {
            targetEl.textContent = rawText;
            return;
        }

        const mathBlocks: string[] = [];
        const protectedText = rawText
            .replace(/\$\$([\s\S]+?)\$\$/g, (match) => {
                const idx = mathBlocks.push(match) - 1;
                return `@@MATHBLOCK${idx}@@`;
            })
            .replace(/\$([^\$\n]+?)\$/g, (match) => {
                const idx = mathBlocks.push(match) - 1;
                return `@@MATHBLOCK${idx}@@`;
            });

        const parsedHtml = w.marked.parse(protectedText, { breaks: true, gfm: true });
        let safeHtml = w.DOMPurify.sanitize(parsedHtml);

        safeHtml = safeHtml.replace(/@@MATHBLOCK(\d+)@@/g, (_: string, id: string) => {
            const expr = mathBlocks[Number(id)] || "";
            return expr.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        });

        targetEl.innerHTML = safeHtml;

        // Inject Copy button into every <pre> code block
        targetEl.querySelectorAll("pre").forEach((preBlock) => {
            const copyBtn = document.createElement("button");
            copyBtn.type = "button";
            copyBtn.textContent = "Copy";
            copyBtn.className =
                "absolute top-2 right-2 px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition";
            copyBtn.onclick = async () => {
                const codeEl = preBlock.querySelector("code");
                const textToCopy = codeEl ? codeEl.innerText : preBlock.innerText;
                await navigator.clipboard.writeText(textToCopy);
                copyBtn.textContent = "Copied!";
                copyBtn.classList.add("text-emerald-400", "border-emerald-500/40");
                setTimeout(() => {
                    copyBtn.textContent = "Copy";
                    copyBtn.classList.remove("text-emerald-400", "border-emerald-500/40");
                }, 1500);
            };
            preBlock.appendChild(copyBtn);
        });

        if (w.renderMathInElement) {
            w.renderMathInElement(targetEl, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "$", right: "$", display: false },
                ],
                throwOnError: false,
            });
        }
    }

    // ---------------------------------------------------------
    // File Upload Handling (.py, .ts, .txt, .log, etc.)
    // ---------------------------------------------------------
    attachFileBtn.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", () => {
        const file = fileInput.files?.[0];
        if (!file) return;

        if (file.size > 250 * 1024) {
            alert("File exceeds 250KB limit for prompt context injection.");
            fileInput.value = "";
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            const content = String(reader.result || "");
            const estTokens = Math.round(content.split(/\s+/).length * 1.3);
            attachedFile = { name: file.name, content, estTokens };
            fileChipLabel.textContent = `📎 ${file.name} (~${estTokens.toLocaleString()} tokens)`;
            fileChip.classList.remove("hidden");
            fileChip.classList.add("flex");
        };
        reader.readAsText(file);
    });

    function clearAttachedFile(): void {
        attachedFile = null;
        fileInput.value = "";
        fileChip.classList.add("hidden");
        fileChip.classList.remove("flex");
    }

    removeFileBtn.addEventListener("click", clearAttachedFile);

    // ---------------------------------------------------------
    // Faculty Demo Presets
    // ---------------------------------------------------------
    document.querySelectorAll(".demo-preset-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const presetPrompt = (btn as HTMLButtonElement).dataset.prompt || "";
            tierOverride.value = ""; // Ensure Auto Route demonstrates the engine
            promptInput.value = presetPrompt;
            promptInput.focus();
        });
    });

    // ---------------------------------------------------------
    // LocalStorage Saved Chats Management
    // ---------------------------------------------------------
    function loadSessions(): ChatSession[] {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch {
            return [];
        }
    }

    function saveSessions(): void {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
        renderSavedChatsList();
    }

    function upsertCurrentSession(): void {
        if (currentMessages.length === 0) return;
        const firstUserMsg = currentMessages.find((m) => m.role === "user");
        const title = firstUserMsg
            ? firstUserMsg.content.slice(0, 36) + (firstUserMsg.content.length > 36 ? "..." : "")
            : "Untitled Chat";

        chatSessionTitle.textContent = title;
        const existingIdx = sessions.findIndex((s) => s.id === activeSessionId);
        const updated: ChatSession = {
            id: activeSessionId,
            title,
            updatedAt: Date.now(),
            messages: [...currentMessages],
        };

        if (existingIdx >= 0) {
            sessions[existingIdx] = updated;
        } else {
            sessions.unshift(updated);
        }
        saveSessions();
    }

    function renderSavedChatsList(): void {
        savedCount.textContent = `${sessions.length}`;
        if (sessions.length === 0) {
            savedChatsList.innerHTML = `<div class="text-slate-500 italic text-[11px]">No saved conversations yet.</div>`;
            return;
        }

        savedChatsList.innerHTML = "";
        for (const sess of sessions) {
            const isActive = sess.id === activeSessionId;
            const row = document.createElement("div");
            row.className = `group flex items-center justify-between px-2.5 py-2 rounded-lg cursor-pointer border transition ${
                isActive
                    ? "bg-sky-500/15 border-sky-500/40 text-sky-300"
                    : "bg-slate-950/60 border-slate-800/80 text-slate-300 hover:border-slate-700"
            }`;

            const titleSpan = document.createElement("span");
            titleSpan.className = "truncate flex-1 pr-2 font-medium";
            titleSpan.textContent = sess.title;
            titleSpan.onclick = () => switchToSession(sess.id);

            const delBtn = document.createElement("button");
            delBtn.className = "text-slate-500 hover:text-rose-400 font-bold px-1 opacity-70 group-hover:opacity-100";
            delBtn.textContent = "×";
            delBtn.title = "Delete chat";
            delBtn.onclick = (e) => {
                e.stopPropagation();
                deleteSession(sess.id);
            };

            row.appendChild(titleSpan);
            row.appendChild(delBtn);
            savedChatsList.appendChild(row);
        }
    }

    async function switchToSession(sessionId: string): Promise<void> {
        if (isStreaming) return;
        const target = sessions.find((s) => s.id === sessionId);
        if (!target) return;

        activeSessionId = target.id;
        currentMessages = [...target.messages];
        chatSessionTitle.textContent = target.title;
        securityBanner.classList.add("hidden");
        resetPipelineNodes();
        renderSavedChatsList();

        // 1. Render all saved message bubbles in the UI
        chatHistory.innerHTML = "";
        for (const msg of currentMessages) {
            const ui = appendMessageBubble(msg.role, msg.content);
            if (msg.role === "assistant" && msg.tierLabel) {
                ui.headerBadge.textContent = `${msg.tierLabel} • ${msg.modelName || ""}`;
                ui.footerMeta.textContent = `Latency: ${msg.latency || "--"} • Est. Cost: ${msg.cost || "--"}`;
            }
        }

        // 2. Exclude blocked turns when syncing restored context back to Redis
        const cleanMessages = currentMessages.filter((m, idx) => {
            if (m.blocked) return false;
            const nextMsg = currentMessages[idx + 1];
            if (m.role === "user" && nextMsg?.blocked) return false;
            return true;
        });

        await fetch("/api/v1/chat/sync/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: activeSessionId,
                messages: cleanMessages.map((m) => ({ role: m.role, content: m.content })),
            }),
        });
    }

    async function deleteSession(sessionId: string): Promise<void> {
        sessions = sessions.filter((s) => s.id !== sessionId);
        saveSessions();
        await fetch("/api/v1/chat/reset/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
        });

        if (sessionId === activeSessionId) {
            startFreshSession();
        }
    }

    function startFreshSession(): void {
        activeSessionId = crypto.randomUUID();
        currentMessages = [];
        clearAttachedFile();
        chatSessionTitle.textContent = "New Conversation";
        chatHistory.innerHTML = `<div class="text-slate-500 italic text-xs">New chat session initialized. Ask a question, attach a file, or select a preset.</div>`;
        securityBanner.classList.add("hidden");
        metricLatency.textContent = "--";
        metricCost.textContent = "--";
        eventBadge.textContent = "IDLE";
        resetPipelineNodes();
        renderSavedChatsList();
    }

    // ---------------------------------------------------------
    // Visual 3-Tier Pipeline Highlighter
    // ---------------------------------------------------------
    function resetPipelineNodes(): void {
        document.querySelectorAll(".tier-node").forEach((el) => {
            el.classList.remove(
                "opacity-100",
                "ring-2",
                "ring-sky-400",
                "ring-emerald-400",
                "ring-purple-400",
                "ring-teal-400",
                "bg-slate-900",
                "border-rose-500"
            );
            el.classList.add("opacity-60");
            const badge = el.querySelector(".node-badge");
            if (badge) {
                badge.textContent = "STANDBY";
                badge.className = "node-badge text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400";
            }
        });
    }

    function highlightPipelineNode(tierKey: string, state: "active" | "failed" = "active"): void {
        const normalizedKey = tierKey.startsWith("CACHE") || tierKey.startsWith("SEMANTIC_CACHE") ? "CACHE" : tierKey;
        const node = document.getElementById(`node-${normalizedKey}`);
        if (!node) return;

        node.classList.remove("opacity-60");
        node.classList.add("opacity-100", "bg-slate-900");
        const badge = node.querySelector(".node-badge");

        if (state === "failed") {
            node.classList.add("border-rose-500");
            if (badge) {
                badge.textContent = "BYPASSED";
                badge.className = "node-badge text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300";
            }
            return;
        }

        const ringMap: Record<string, string> = {
            CACHE: "ring-teal-400",
            TIER_1_LOCAL_LIGHT: "ring-emerald-400",
            TIER_2_CLOUD_LIGHT: "ring-sky-400",
            TIER_3_CLOUD_HEAVY: "ring-purple-400",
        };
        node.classList.add("ring-2", ringMap[normalizedKey] || "ring-sky-400");

        if (badge) {
            badge.textContent = "ACTIVE";
            badge.className = "node-badge text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 animate-pulse";
        }
    }

    // ---------------------------------------------------------
    // Hardware Telemetry Polling
    // ---------------------------------------------------------
    async function refreshHardwareHealth() {
        try {
            const res = await fetch("/api/v1/health/");
            if (!res.ok) return;
            const data = await res.json();
            hwCpu.textContent = `${data.cpu_percent}%`;
            hwRam.textContent = `${data.ram_percent}%`;
            hwVram.textContent = data.vram_total_mb > 0 ? `${data.vram_percent}% (${data.vram_used_mb}MB)` : "N/A";
            hwStatus.textContent = data.healthy ? "HEALTHY" : "DEGRADED";
            hwStatus.className = data.healthy ? "text-emerald-400 font-mono" : "text-rose-400 font-mono";

            hwBadge.textContent = data.healthy
                ? `Edge Ready • RAM ${data.ram_percent}%`
                : `Edge Bypass (${data.reason})`;
            hwBadge.className = data.healthy
                ? "px-3 py-1 rounded-full text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "px-3 py-1 rounded-full text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20";
        } catch {
            hwBadge.textContent = "Telemetry Offline";
        }
    }

    refreshHardwareHealth();
    setInterval(refreshHardwareHealth, 8000);
    renderSavedChatsList();

    // ---------------------------------------------------------
    // Chat Message Bubble Renderer
    // ---------------------------------------------------------
    function appendMessageBubble(role: "user" | "assistant", initialText: string = "") {
        if (chatHistory.querySelector(".italic")) {
            chatHistory.innerHTML = "";
        }

        const wrapper = document.createElement("div");
        wrapper.className = role === "user" ? "flex justify-end" : "flex justify-start";

        const bubble = document.createElement("div");
        bubble.className = role === "user"
            ? "bg-sky-600/20 border border-sky-500/30 text-slate-100 rounded-xl px-4 py-2.5 max-w-[80%] whitespace-pre-wrap"
            : "bg-slate-950 border border-slate-800 text-slate-200 rounded-xl px-4 py-3 max-w-[88%] space-y-2";

        const headerBadge = document.createElement("div");
        headerBadge.className = role === "assistant"
            ? "inline-block text-[10px] font-mono px-2 py-0.5 rounded border bg-slate-900 text-sky-300 border-slate-700"
            : "hidden";
        headerBadge.textContent = "Routing...";

        const bodyDiv = document.createElement("div");
        bodyDiv.className = role === "assistant"
            ? "markdown-body text-sm text-slate-200"
            : "whitespace-pre-wrap text-sm";

        if (role === "assistant" && initialText) {
            renderFormattedContent(bodyDiv, initialText);
        } else {
            bodyDiv.textContent = initialText;
        }

        const footerMeta = document.createElement("div");
        footerMeta.className = role === "assistant"
            ? "text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/80"
            : "hidden";

        if (role === "assistant") {
            bubble.appendChild(headerBadge);
        }
        bubble.appendChild(bodyDiv);
        if (role === "assistant") {
            bubble.appendChild(footerMeta);
        }

        wrapper.appendChild(bubble);
        chatHistory.appendChild(wrapper);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        return { bodyDiv, headerBadge, footerMeta };
    }

    // ---------------------------------------------------------
    // Send / Stop Stream Button State
    // ---------------------------------------------------------
    function setStreamingState(streaming: boolean): void {
        isStreaming = streaming;
        if (streaming) {
            sendBtn.textContent = "Stop";
            sendBtn.className = "px-6 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-xl transition-colors text-sm min-w-[96px]";
        } else {
            sendBtn.textContent = "Send";
            sendBtn.className = "px-6 bg-sky-600 hover:bg-sky-500 text-white font-semibold rounded-xl transition-colors text-sm min-w-[96px]";
        }
    }

    newChatBtn.addEventListener("click", async () => {
        if (isStreaming && currentAbortController) {
            currentAbortController.abort();
        }
        await fetch("/api/v1/chat/reset/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: activeSessionId }),
        });
        startFreshSession();
    });

    promptInput.addEventListener("keydown", (e: KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!isStreaming) {
                sendBtn.click();
            }
        }
    });

    sendBtn.addEventListener("click", async () => {
        // If currently streaming, abort immediately
        if (isStreaming && currentAbortController) {
            currentAbortController.abort();
            return;
        }

        const rawPrompt = promptInput.value.trim();
        if (!rawPrompt && !attachedFile) return;

        const displayPrompt = attachedFile
            ? `${rawPrompt || "Analyze this attached file."}\n\n📎 Attached: ${attachedFile.name} (~${attachedFile.estTokens} tokens)`
            : rawPrompt;

        const fullPayloadPrompt = attachedFile
            ? `${rawPrompt || "Analyze this attached file."}\n\n[Attached File: ${attachedFile.name}]\n\`\`\`\n${attachedFile.content}\n\`\`\``
            : rawPrompt;

        const selectedOverride = tierOverride.value;

        promptInput.value = "";
        clearAttachedFile();
        securityBanner.classList.add("hidden");
        resetPipelineNodes();

        appendMessageBubble("user", displayPrompt);
        currentMessages.push({ role: "user", content: displayPrompt });
        upsertCurrentSession();

        const assistantUI = appendMessageBubble("assistant", "");
        const assistantRecord: StoredMessage = { role: "assistant", content: "" };

        metricLatency.textContent = "...";
        metricCost.textContent = "...";
        eventBadge.textContent = "STREAMING";
        eventBadge.className = "text-xs font-mono text-sky-400 animate-pulse";

        currentAbortController = new AbortController();
        setStreamingState(true);

        try {
            const response = await fetch("/api/v1/route/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: fullPayloadPrompt,
                    session_id: activeSessionId,
                    forced_tier: selectedOverride,
                }),
                signal: currentAbortController.signal,
            });

            if (!response.ok || !response.body) {
                throw new Error(`HTTP Error: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                let currentEvent = "";
                for (const line of lines) {
                    if (line.startsWith("event: ")) {
                        currentEvent = line.replace("event: ", "").trim();
                    } else if (line.startsWith("data: ")) {
                        const rawData = line.replace("data: ", "").trim();
                        try {
                            const parsed = JSON.parse(rawData);
                            handleSSEEvent(currentEvent, parsed, assistantUI, assistantRecord);
                        } catch (err) {
                            console.error("JSON parse error:", err);
                        }
                    }
                }
            }
        } catch (err: any) {
            if (err.name === "AbortError") {
                assistantRecord.content += "\n\n*[Generation stopped by user]*";
                renderFormattedContent(assistantUI.bodyDiv, assistantRecord.content);
                eventBadge.textContent = "STOPPED";
                eventBadge.className = "text-xs font-mono text-amber-400";
                document.querySelectorAll(".node-badge").forEach((b) => b.classList.remove("animate-pulse"));
            } else {
                assistantUI.bodyDiv.textContent = `[Client Error]: ${err.message}`;
                assistantRecord.content = assistantUI.bodyDiv.textContent;
                eventBadge.textContent = "FAILED";
                eventBadge.className = "text-xs font-mono text-rose-400";
            }
        } finally {
            currentAbortController = null;
            setStreamingState(false);
            currentMessages.push(assistantRecord);
            upsertCurrentSession();
            refreshHardwareHealth();
        }
    });

    function handleSSEEvent(
        event: string,
        data: any,
        ui: { bodyDiv: HTMLDivElement; headerBadge: HTMLDivElement; footerMeta: HTMLDivElement },
        record: StoredMessage
    ) {
        switch (event) {
            case "security": {
                const entities: string[] = data.detected_entities || data.masked_entities || [];
                securityBanner.className =
                    "shrink-0 bg-rose-500/15 border border-rose-500/40 text-rose-300 px-4 py-2 rounded-xl text-xs font-mono";
                securityBanner.textContent = `🛑 DLP SECURITY BLOCK: Prompt rejected (${entities.join(", ")}) — Request was NOT sent to any LLM.`;
                securityBanner.classList.remove("hidden");
                break;
            }

            case "blocked": {
                resetPipelineNodes();
                const entities: string[] = data.detected_entities || [];
                ui.headerBadge.className =
                    "inline-block text-[10px] font-mono px-2 py-0.5 rounded border bg-rose-500/20 text-rose-300 border-rose-500/40";
                ui.headerBadge.textContent = "DLP GUARDRAIL • BLOCKED";

                record.tierLabel = "DLP GUARDRAIL";
                record.modelName = "BLOCKED";
                record.blocked = true;
                record.content =
                    `### 🛑 Prompt Blocked by Security Policy\n\n` +
                    `This prompt cannot be passed to any model because sensitive information was detected:\n` +
                    `- **Detected Entities:** \`${entities.join("`, `")}\`\n\n` +
                    `Please remove all email addresses, API keys, phone numbers, IDs, or IP addresses and try again.`;

                renderFormattedContent(ui.bodyDiv, record.content);

                metricLatency.textContent = data.latency_ms || "0 ms";
                metricCost.textContent = "$0.0000";
                ui.footerMeta.textContent = `Blocked at Gateway (${data.latency_ms || "0 ms"}) • 0 LLM Calls • $0.0000`;
                record.latency = data.latency_ms || "0 ms";
                record.cost = "$0.0000";

                eventBadge.textContent = "BLOCKED (DLP)";
                eventBadge.className = "text-xs font-mono text-rose-400 font-semibold";
                break;
            }

            case "metrics":
                scoreComplexity.textContent = `${data.complexity_score}${data.overridden ? " (Manual)" : ""}`;
                scoreTokens.textContent = `${data.total_context_tokens}`;
                break;

            case "status": {
                resetPipelineNodes();
                highlightPipelineNode(String(data.tier || ""), "active");

                const key: string = data.status === "cache_hit" ? "CACHE" : String(data.tier || "");
                const meta = TIER_META[key] || {
                    label: String(data.tier || "UNKNOWN"),
                    model: String(data.model_name || ""),
                    badgeClass: "bg-slate-800 text-sky-300 border-slate-700",
                };
                const resolvedModel = String(data.model_name || meta.model);

                ui.headerBadge.className = `inline-block text-[10px] font-mono px-2 py-0.5 rounded border ${meta.badgeClass}`;
                ui.headerBadge.textContent = `${meta.label} • ${resolvedModel}`;
                record.tierLabel = meta.label;
                record.modelName = resolvedModel;

                eventBadge.textContent = data.status === "cache_hit" ? "SEMANTIC CACHE HIT" : `EXECUTING (${resolvedModel})`;
                break;
            }

            case "message":
                record.content += data.text;
                renderFormattedContent(ui.bodyDiv, record.content);
                chatHistory.scrollTop = chatHistory.scrollHeight;
                break;

            case "fallback":
                highlightPipelineNode(String(data.failed_tier || ""), "failed");
                record.content += `\n\n> ⚠️ **FALLBACK:** \`${data.failed_tier}\` failed (${data.reason}). Escalating tier...\n\n`;
                renderFormattedContent(ui.bodyDiv, record.content);
                break;

            case "complete":
                metricLatency.textContent = data.latency_ms;
                metricCost.textContent = data.cost;
                ui.footerMeta.textContent = `Latency: ${data.latency_ms} • Est. Cost: ${data.cost}`;
                record.latency = data.latency_ms;
                record.cost = data.cost;

                document.querySelectorAll(".node-badge").forEach((b) => b.classList.remove("animate-pulse"));
                eventBadge.textContent = "COMPLETED";
                eventBadge.className = "text-xs font-mono text-emerald-400";
                break;

            case "error":
                record.content += `\n\n> ❌ **FATAL ERROR:** ${data.error_details}`;
                renderFormattedContent(ui.bodyDiv, record.content);
                eventBadge.textContent = "ERROR";
                eventBadge.className = "text-xs font-mono text-rose-500";
                break;
        }
    }

    // ---------------------------------------------------------
    // Analytics Modal & Chart.js Rendering
    // ---------------------------------------------------------
    async function loadAnalyticsModal(): Promise<void> {
        const res = await fetch("/api/v1/analytics/");
        if (!res.ok) return;
        const data = await res.json();

        (document.getElementById("stat-total-req") as HTMLElement).textContent = `${data.total_requests}`;
        (document.getElementById("stat-cost-saved") as HTMLElement).textContent = `$${data.total_saved.toFixed(4)} (${data.savings_percent}%)`;
        (document.getElementById("stat-cache-rate") as HTMLElement).textContent = `${data.cache_hit_rate}%`;
        (document.getElementById("stat-pii-count") as HTMLElement).textContent = `${data.pii_events}`;

        const tbody = document.getElementById("analytics-audit-body") as HTMLTableSectionElement;
        tbody.innerHTML = "";
        if (!data.recent_logs || data.recent_logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="py-3 text-slate-500 italic">No telemetry recorded yet. Send a prompt to populate metrics.</td></tr>`;
        } else {
            for (const row of data.recent_logs) {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td class="py-2 pr-3 text-slate-400">${row.timestamp}</td>
                    <td class="py-2 pr-3 text-sky-300">${row.tier}</td>
                    <td class="py-2 pr-3">${row.model_name}</td>
                    <td class="py-2 pr-3 text-amber-300">${row.latency_ms} ms</td>
                    <td class="py-2 pr-3 text-emerald-400">$${Number(row.cost).toFixed(4)}</td>
                    <td class="py-2">${row.pii_redacted ? "🛡️ PII Masked" : row.cache_hit ? "⚡ Cache Hit" : "Clean"}</td>
                `;
                tbody.appendChild(tr);
            }
        }

        const ChartLib = (window as any).Chart;
        if (!ChartLib) return;

        if (tierChartInstance) tierChartInstance.destroy();
        if (latencyChartInstance) latencyChartInstance.destroy();

        const labels = ["Semantic Cache", "Tier 1 (Local)", "Tier 2 (Cloud Lite)", "Tier 3 (Cloud Heavy)"];
        const tierKeys = ["CACHE", "TIER_1_LOCAL_LIGHT", "TIER_2_CLOUD_LIGHT", "TIER_3_CLOUD_HEAVY"];

        const tierCanvas = document.getElementById("tierDistributionChart") as HTMLCanvasElement;
        tierChartInstance = new ChartLib(tierCanvas, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    data: tierKeys.map((k) => data.tier_counts[k] || 0),
                    backgroundColor: ["#14b8a6", "#10b981", "#0ea5e9", "#a855f7"],
                    borderColor: "#020617",
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "bottom", labels: { color: "#cbd5e1", font: { size: 11 } } },
                },
            },
        });

        const latencyCanvas = document.getElementById("latencyComparisonChart") as HTMLCanvasElement;
        latencyChartInstance = new ChartLib(latencyCanvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "Avg Latency (ms)",
                    data: tierKeys.map((k) => data.avg_latency_ms[k] || 0),
                    backgroundColor: ["rgba(20,184,166,0.7)", "rgba(16,185,129,0.7)", "rgba(14,165,233,0.7)", "rgba(168,85,247,0.7)"],
                    borderRadius: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { color: "#1e293b" } },
                    y: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { color: "#1e293b" } },
                },
            },
        });
    }

    openAnalyticsBtn.addEventListener("click", async () => {
        analyticsModal.classList.remove("hidden");
        await loadAnalyticsModal();
    });

    closeAnalyticsBtn.addEventListener("click", () => {
        analyticsModal.classList.add("hidden");
    });

    analyticsModal.addEventListener("click", (e) => {
        if (e.target === analyticsModal) {
            analyticsModal.classList.add("hidden");
        }
    });

    resetAnalyticsBtn.addEventListener("click", async () => {
        await fetch("/api/v1/analytics/", { method: "POST" });
        await loadAnalyticsModal();
    });
});