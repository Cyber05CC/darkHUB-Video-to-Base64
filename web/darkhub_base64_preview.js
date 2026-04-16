import { app } from "../../scripts/app.js";

function normalizeBase64Payload(base64Data) {
    if (!base64Data) {
        return "";
    }
    return base64Data.startsWith("data:") ? base64Data.split(",")[1] : base64Data;
}

function downloadBlob(base64Data, mimeType, filename) {
    const payload = normalizeBase64Payload(base64Data);
    if (!payload) {
        throw new Error("No Base64 payload available for download.");
    }

    const byteChars = atob(payload);
    const bytes = new Uint8Array(byteChars.length);
    for (let index = 0; index < byteChars.length; index += 1) {
        bytes[index] = byteChars.charCodeAt(index);
    }

    const blob = new Blob([bytes], { type: mimeType || "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "darkhub_output";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadText(text, filename) {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "darkhub_base64.txt";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function copyToClipboard(text) {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
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

function createButton(label, backgroundColor, onClick) {
    const button = document.createElement("button");
    button.dataset.label = label;
    button.textContent = label;
    button.style.cssText = `
        width: 100%;
        padding: 8px 12px;
        margin: 4px 0 0;
        border: none;
        border-radius: 6px;
        background: ${backgroundColor};
        color: #ffffff;
        font-weight: 700;
        font-size: 12px;
        cursor: pointer;
        transition: opacity 0.18s ease;
    `;

    button.addEventListener("mouseenter", () => {
        button.style.opacity = "0.88";
    });
    button.addEventListener("mouseleave", () => {
        button.style.opacity = "1";
    });
    button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
            await onClick(button);
        } catch (error) {
            console.error("[darkHUB Base64 Nodes]", error);
            setTemporaryLabel(button, "Action failed");
        }
    });

    return button;
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
    container.style.cssText = "padding: 4px 8px 6px; width: 100%; box-sizing: border-box;";

    const widget = node.addDOMWidget(widgetName, "custom", container, {
        serialize: false,
        hideOnZoom: false,
    });

    return { widget, element: container };
}

function appendStatusBlock(element, text, color = "#4caf50") {
    const status = document.createElement("div");
    status.style.cssText = `
        color: ${color};
        font-size: 12px;
        margin-bottom: 6px;
        white-space: pre-wrap;
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        line-height: 1.45;
    `;
    status.textContent = text;
    element.appendChild(status);
}

function appendPreviewBlock(element, base64Data, explicitPreview) {
    const preview = document.createElement("div");
    preview.style.cssText = `
        color: #a8adb7;
        font-size: 10px;
        margin-bottom: 8px;
        word-break: break-all;
        max-height: 52px;
        overflow: hidden;
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        line-height: 1.35;
    `;
    const raw = explicitPreview || normalizeBase64Payload(base64Data);
    preview.textContent = raw;
    element.appendChild(preview);
}

function extractMessageValue(message, key) {
    const value = message?.[key];
    return Array.isArray(value) ? value[0] : value;
}

function appendBase64Panel(element, config) {
    const {
        status,
        base64Data,
        base64Preview,
        mimeType,
        mediaFilename,
        textFilename,
        fileSize,
        downloadsPath,
        accentColor,
    } = config;

    appendStatusBlock(element, status || "Base64 ready.", accentColor || "#4caf50");

    if (base64Data || base64Preview) {
        appendPreviewBlock(element, base64Data, base64Preview);
    }

    if (downloadsPath) {
        appendStatusBlock(element, `Downloads copy: ${downloadsPath}`, "#c7ccd4");
    }

    if (base64Data && mimeType) {
        const extension = mediaFilename ? mediaFilename.split(".").pop().toUpperCase() : "FILE";
        element.appendChild(
            createButton(`Download ${extension} (${fileSize || "unknown"})`, "#1e7a31", async (button) => {
                downloadBlob(base64Data, mimeType, mediaFilename || "darkhub_output");
                setTemporaryLabel(button, "Download started");
            }),
        );
    }

    if (base64Data) {
        element.appendChild(
            createButton("Copy Base64", "#245e9b", async (button) => {
                await copyToClipboard(base64Data);
                setTemporaryLabel(button, "Copied");
            }),
        );

        element.appendChild(
            createButton("Download Base64 TXT", "#6640a8", async (button) => {
                downloadText(base64Data, textFilename || "darkhub_base64.txt");
                setTemporaryLabel(button, "TXT saved");
            }),
        );
    }
}

app.registerExtension({
    name: "darkHUB.Base64Nodes",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "DarkHubVideoToBase64") {
            const originalOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function onExecuted(message) {
                originalOnExecuted?.apply(this, arguments);
                if (!message) {
                    return;
                }

                const { element } = getOrCreateContainer(this, "darkhub_controls");
                appendBase64Panel(element, {
                    status: extractMessageValue(message, "text"),
                    base64Data: extractMessageValue(message, "base64_data"),
                    base64Preview: extractMessageValue(message, "base64_preview"),
                    mimeType: extractMessageValue(message, "mime_type"),
                    mediaFilename: extractMessageValue(message, "media_filename"),
                    textFilename: extractMessageValue(message, "txt_filename"),
                    fileSize: extractMessageValue(message, "file_size"),
                    downloadsPath: extractMessageValue(message, "downloads_text_path"),
                    accentColor: "#4caf50",
                });
                this.setSize(this.computeSize());
            };
        }

        if (nodeData.name === "DarkHubBase64ToImage") {
            const originalOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function onExecuted(message) {
                originalOnExecuted?.apply(this, arguments);
                if (!message) {
                    return;
                }

                const { element } = getOrCreateContainer(this, "darkhub_decode_status");
                appendBase64Panel(element, {
                    status: extractMessageValue(message, "text"),
                    base64Data: extractMessageValue(message, "base64_data"),
                    base64Preview: extractMessageValue(message, "base64_preview"),
                    mimeType: extractMessageValue(message, "mime_type"),
                    mediaFilename: extractMessageValue(message, "media_filename"),
                    textFilename: extractMessageValue(message, "txt_filename"),
                    fileSize: extractMessageValue(message, "file_size"),
                    downloadsPath: extractMessageValue(message, "downloads_text_path") || extractMessageValue(message, "downloads_path"),
                    accentColor: "#6bd1ff",
                });
                this.setSize(this.computeSize());
            };
        }

        if (nodeData.name === "DarkHubBase64Info") {
            const originalOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function onExecuted(message) {
                originalOnExecuted?.apply(this, arguments);
                if (!message?.text) {
                    return;
                }

                const infoText = extractMessageValue(message, "text");
                const { element } = getOrCreateContainer(this, "darkhub_info");
                appendStatusBlock(element, infoText, "#d6d9df");
                this.setSize(this.computeSize());
            };
        }
    },
});
