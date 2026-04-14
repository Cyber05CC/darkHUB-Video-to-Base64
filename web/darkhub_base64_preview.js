import { app } from "../../scripts/app.js";

function downloadBlob(base64Data, mimeType, filename) {
    let payload = base64Data;
    if (payload.startsWith("data:")) {
        payload = payload.split(",")[1];
    }

    const byteChars = atob(payload);
    const bytes = new Uint8Array(byteChars.length);
    for (let index = 0; index < byteChars.length; index += 1) {
        bytes[index] = byteChars.charCodeAt(index);
    }

    const blob = new Blob([bytes], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
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
    anchor.download = filename;
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

function appendPreviewBlock(element, base64Data) {
    const preview = document.createElement("div");
    preview.style.cssText = `
        color: #a8adb7;
        font-size: 10px;
        margin-bottom: 8px;
        word-break: break-all;
        max-height: 36px;
        overflow: hidden;
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        line-height: 1.35;
    `;
    const raw = base64Data.startsWith("data:") ? base64Data.split(",")[1] : base64Data;
    preview.textContent = raw.length > 88 ? `${raw.substring(0, 88)}...` : raw;
    element.appendChild(preview);
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

                const base64Data = Array.isArray(message.base64_data) ? message.base64_data[0] : message.base64_data;
                const mimeType = Array.isArray(message.mime_type) ? message.mime_type[0] : message.mime_type;
                const status = Array.isArray(message.text) ? message.text[0] : message.text;
                const mediaFilename = Array.isArray(message.media_filename) ? message.media_filename[0] : message.media_filename;
                const textFilename = Array.isArray(message.txt_filename) ? message.txt_filename[0] : message.txt_filename;
                const fileSize = Array.isArray(message.file_size) ? message.file_size[0] : message.file_size;

                if (!base64Data) {
                    return;
                }

                const { element } = getOrCreateContainer(this, "darkhub_controls");

                appendStatusBlock(element, status || "Base64 ready.");
                appendPreviewBlock(element, base64Data);

                const extension = mediaFilename ? mediaFilename.split(".").pop().toUpperCase() : "FILE";

                element.appendChild(
                    createButton(`Download ${extension} (${fileSize || "unknown"})`, "#1e7a31", async (button) => {
                        downloadBlob(base64Data, mimeType, mediaFilename || "darkhub_output");
                        setTemporaryLabel(button, "Download started");
                    }),
                );

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

                const status = Array.isArray(message.text) ? message.text[0] : message.text;
                const downloadsPath = Array.isArray(message.downloads_path) ? message.downloads_path[0] : message.downloads_path;
                const { element } = getOrCreateContainer(this, "darkhub_decode_status");

                let text = status || "Decode complete.";
                if (downloadsPath) {
                    text += "\nDownloads copy saved.";
                }

                appendStatusBlock(element, text);
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

                const infoText = Array.isArray(message.text) ? message.text[0] : message.text;
                const { element } = getOrCreateContainer(this, "darkhub_info");
                appendStatusBlock(element, infoText, "#d6d9df");
                this.setSize(this.computeSize());
            };
        }
    },
});
