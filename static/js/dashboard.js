document.addEventListener("DOMContentLoaded", () => {
    const sendBtn = document.getElementById("send-btn");
    const promptInput = document.getElementById("prompt-input");
    const outputBox = document.getElementById("output-box");
    const metricTier = document.getElementById("metric-tier");
    const metricLatency = document.getElementById("metric-latency");
    const metricCost = document.getElementById("metric-cost");
    const eventBadge = document.getElementById("event-badge");
    sendBtn.addEventListener("click", async () => {
        const prompt = promptInput.value.trim();
        if (!prompt)
            return;
        // Reset UI State
        sendBtn.disabled = true;
        sendBtn.textContent = "Routing & Executing...";
        outputBox.textContent = "";
        metricTier.textContent = "Analyzing...";
        metricLatency.textContent = "...";
        metricCost.textContent = "...";
        eventBadge.textContent = "CONNECTING";
        eventBadge.className = "text-xs font-mono text-sky-400 animate-pulse";
        try {
            const response = await fetch("/api/v1/route/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt })
            });
            if (!response.ok || !response.body) {
                throw new Error(`HTTP Error: ${response.status}`);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done)
                    break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || ""; // Retain incomplete chunk in buffer
                let currentEvent = "";
                for (const line of lines) {
                    if (line.startsWith("event: ")) {
                        currentEvent = line.replace("event: ", "").trim();
                    }
                    else if (line.startsWith("data: ")) {
                        const rawData = line.replace("data: ", "").trim();
                        try {
                            const parsed = JSON.parse(rawData);
                            handleSSEEvent(currentEvent, parsed);
                        }
                        catch (err) {
                            console.error("JSON parse error:", err);
                        }
                    }
                }
            }
        }
        catch (err) {
            outputBox.textContent = `[Client Stream Error]: ${err.message}`;
            eventBadge.textContent = "FAILED";
            eventBadge.className = "text-xs font-mono text-rose-400";
        }
        finally {
            sendBtn.disabled = false;
            sendBtn.textContent = "Route & Stream";
        }
    });
    function handleSSEEvent(event, data) {
        switch (event) {
            case "status":
                const statusData = data;
                metricTier.textContent = statusData.tier;
                eventBadge.textContent = `EXECUTING (${statusData.tier})`;
                break;
            case "message":
                outputBox.textContent += data.text;
                outputBox.scrollTop = outputBox.scrollHeight;
                break;
            case "fallback":
                outputBox.textContent += `\n\n⚠️ [SYSTEM FALLBACK]: ${data.failed_tier} failed (${data.reason}). Switching tier...\n\n`;
                break;
            case "complete":
                const comp = data;
                metricTier.textContent = comp.routed_tier;
                metricLatency.textContent = comp.latency_ms;
                metricCost.textContent = comp.cost;
                eventBadge.textContent = "COMPLETED";
                eventBadge.className = "text-xs font-mono text-emerald-400";
                break;
            case "error":
                outputBox.textContent += `\n\n❌ [FATAL ERROR]: ${data.error_details}`;
                eventBadge.textContent = "ERROR";
                eventBadge.className = "text-xs font-mono text-rose-500";
                break;
        }
    }
});
