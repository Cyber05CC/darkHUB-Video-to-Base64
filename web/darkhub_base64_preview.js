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

function getOrCreateContainer(node, widgetName) {
    const existingWidget = node.widgets?.find((widget) => widget.name === widgetName);
    if (existingWidget) {
        const element = existingWidget.element || existingWidget.inputEl;
        if (element) {
            element.innerHTML = "";
            return element;
        }
    }

    const container = document.createElement("div");
    container.style.cssText = "padding: 6px 8px 8px; width: 100%; box-sizing: border-box;";
    node.addDOMWidget(widgetName, "custom", container, {
        serialize: false,
        hideOnZoom: false,
    });
    return container;
}

function renderCopyButton(element, base64Data) {
    element.innerHTML = "";

    const button = document.createElement("button");
    button.dataset.label = "Copy Base64";
    button.textContent = "Copy Base64";
    button.disabled = !base64Data;
    button.style.cssText = `
        width: 100%;
        padding: 12px 14px;
        border: none;
        border-radius: 10px;
        background: #1f7ae0;
        color: #ffffff;
        font-weight: 800;
        font-size: 12px;
        cursor: ${base64Data ? "pointer" : "not-allowed"};
        opacity: ${base64Data ? "1" : "0.55"};
        box-sizing: border-box;
    `;

    if (base64Data) {
        button.addEventListener("click", async (event) => {
            event.preventDefault();
            event.stopPropagation();
            try {
                await copyToClipboard(base64Data);
                setTemporaryLabel(button, "Copied");
            } catch (error) {
                console.error("[darkHUB Base64]", error);
                setTemporaryLabel(button, "Copy failed");
            }
        });
    }

    element.appendChild(button);
}

function refreshNodeSize(node) {
    window.requestAnimationFrame(() => {
        const nextSize = node.computeSize();
        nextSize[0] = Math.max(nextSize[0], 220);
        node.setSize(nextSize);
    });
}

app.registerExtension({
    name: "darkHUB.CopyBase64",

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

            const container = getOrCreateContainer(this, "darkhub_copy_button");
            renderCopyButton(container, extractMessageValue(message, "base64_data"));
            refreshNodeSize(this);
        };
    },
});