import { app } from "../../scripts/app.js";

async function copyToClipboard(text) {
    if (!text) {
        throw new Error("No Base64 payload is available to copy.");
    }

    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    textArea.style.pointerEvents = "none";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    document.execCommand("copy");
    document.body.removeChild(textArea);
}

function setTemporaryLabel(button, label, timeout = 1400) {
    const original = button.dataset.label ?? button.textContent;
    button.textContent = label;
    window.clearTimeout(button._restoreTimer);
    button._restoreTimer = window.setTimeout(() => {
        button.textContent = original;
    }, timeout);
}

function extractMessageValue(message, key) {
    const value = message?.[key];
    return Array.isArray(value) ? value[0] : value;
}

function formatNumber(value) {
    if (value === undefined || value === null || value === "") {
        return "-";
    }
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
        return numeric.toLocaleString();
    }
    return String(value);
}

function getOrCreateContainer(node, widgetName) {
    const existingWidget = node.widgets?.find((widget) => widget.name === widgetName);
    if (existingWidget) {
        const element = existingWidget.element || existingWidget.inputEl;
        if (element) {
            element.innerHTML = "";
            return { widget: existingWidget, element };
        }
    }

    const container = document.createElement("div");
    container.style.cssText = "padding: 6px 8px 8px; width: 100%; box-sizing: border-box;";

    const widget = node.addDOMWidget(widgetName, "custom", container, {
        serialize: false,
        hideOnZoom: false,
    });

    return { widget, element: container };
}

function createMetaChip(label, value) {
    const chip = document.createElement("div");
    chip.style.cssText = `
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(109, 209, 255, 0.1);
        border: 1px solid rgba(109, 209, 255, 0.18);
        color: #d7ecff;
        font-size: 11px;
        line-height: 1;
        min-width: 0;
        box-sizing: border-box;
    `;

    const labelEl = document.createElement("span");
    labelEl.style.cssText = "color: #8db8d8; font-weight: 600;";
    labelEl.textContent = `${label}:`;

    const valueEl = document.createElement("span");
    valueEl.style.cssText = "color: #f3f8ff; font-weight: 700;";
    valueEl.textContent = value;

    chip.append(labelEl, valueEl);
    return chip;
}

function createCopyButton(base64Data, mimeType) {
    const button = document.createElement("button");
    const label = mimeType?.includes("video") ? "Copy Base64 (MP4)" : "Copy Base64 (PNG)";
    button.dataset.label = label;
    button.textContent = label;
    button.disabled = !base64Data;
    button.style.cssText = `
        width: 100%;
        padding: 11px 14px;
        border: none;
        border-radius: 10px;
        background: linear-gradient(135deg, #1f7ae0, #0aa56f);
        color: #ffffff;
        font-weight: 800;
        font-size: 12px;
        letter-spacing: 0.02em;
        cursor: ${base64Data ? "pointer" : "not-allowed"};
        opacity: ${base64Data ? "1" : "0.55"};
        transition: opacity 0.18s ease, transform 0.18s ease;
    `;

    if (base64Data) {
        button.addEventListener("mouseenter", () => {
            button.style.opacity = "0.9";
            button.style.transform = "translateY(-1px)";
        });
        button.addEventListener("mouseleave", () => {
            button.style.opacity = "1";
            button.style.transform = "translateY(0)";
        });
        button.addEventListener("click", async (event) => {
            event.preventDefault();
            event.stopPropagation();
            try {
                await copyToClipboard(base64Data);
                setTemporaryLabel(button, "Copied");
            } catch (error) {
                console.error("[darkHUB Base64 Nodes]", error);
                setTemporaryLabel(button, "Copy failed");
            }
        });
    }

    return button;
}

function renderCopyPanel(element, config) {
    element.innerHTML = "";

    const card = document.createElement("div");
    card.style.cssText = `
        display: flex;
        flex-direction: column;
        gap: 10px;
        width: 100%;
        box-sizing: border-box;
        padding: 12px;
        border-radius: 12px;
        border: 1px solid rgba(109, 209, 255, 0.18);
        background: linear-gradient(180deg, rgba(20, 24, 30, 0.98), rgba(14, 17, 22, 0.98));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
        overflow: hidden;
    `;

    const title = document.createElement("div");
    title.style.cssText = "color: #f6fbff; font-size: 13px; font-weight: 800; letter-spacing: 0.02em;";
    title.textContent = "Base64 Storage";

    const subtitle = document.createElement("div");
    subtitle.style.cssText = `
        color: #a8b8c7;
        font-size: 11px;
        line-height: 1.5;
        word-break: break-word;
    `;
    subtitle.textContent = config.status || "The latest Base64 result is stored in the node and can be copied at any time.";

    const chips = document.createElement("div");
    chips.style.cssText = "display: flex; flex-wrap: wrap; gap: 6px; width: 100%;";
    chips.append(
        createMetaChip("Format", config.mimeType || "-"),
        createMetaChip("Frames", formatNumber(config.frameCount)),
        createMetaChip("Chars", formatNumber(config.base64Length)),
        createMetaChip("Size", config.fileSize || "-"),
        createMetaChip("Audio", config.hasAudio ? "embedded" : "none"),
    );

    card.append(title, subtitle, chips, createCopyButton(config.base64Data, config.mimeType));
    element.appendChild(card);
}

function refreshNodeSize(node) {
    window.requestAnimationFrame(() => {
        const nextSize = node.computeSize();
        nextSize[0] = Math.max(nextSize[0], 320);
        node.setSize(nextSize);
    });
}

app.registerExtension({
    name: "darkHUB.Base64CopyOnly",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "DarkHubVideoToBase64") {
            return;
        }

        const originalOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function onExecuted(message) {
            originalOnExecuted?.apply(this, arguments);
            if (!message) {
                return;
            }

            const { element } = getOrCreateContainer(this, "darkhub_copy_panel");
            renderCopyPanel(element, {
                status: extractMessageValue(message, "text"),
                base64Data: extractMessageValue(message, "base64_data"),
                mimeType: extractMessageValue(message, "mime_type"),
                frameCount: extractMessageValue(message, "frame_count"),
                base64Length: extractMessageValue(message, "base64_length"),
                fileSize: extractMessageValue(message, "file_size"),
                hasAudio: Boolean(extractMessageValue(message, "has_audio")),
            });
            refreshNodeSize(this);
        };
    },
});