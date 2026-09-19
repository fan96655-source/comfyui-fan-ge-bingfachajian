import { app } from "../../../scripts/app.js";

// Keep these keys equal to the Python input/output names.  Only the visible
// label changes; workflow JSON continues to use the stable English keys.
const RH_NODE_TYPE = "RHDirectStrongModelFan";

const INPUT_DISPLAY_NAMES = {
  image1: "🖼️ 参考图1",
  image2: "🖼️ 参考图2",
  image3: "🖼️ 参考图3",
  image4: "🖼️ 参考图4",
  image5: "🖼️ 参考图5",
  image6: "🖼️ 参考图6",
  image7: "🖼️ 参考图7",
  image8: "🖼️ 参考图8",
  image9: "🖼️ 参考图9",
  image10: "🖼️ 参考图10",
  api_channel: "🌐 API线路",
  api_key: "🔑 API密钥",
  custom_api_url: "🔗 自定义API地址",
  prompt: "📝 提示词",
  prompt_strength: "🎯 prompt强度",
  ref_strength: "🧷 参考图强度",
  model: "⚙️ 参数控制区 · 🤖 模型版本",
  aspect_ratio: "├── 📐 宽高比",
  resolution: "├── 🖼️ 分辨率",
  seed: "├── 🎲 seed",
  randomize: "└── 🔀 randomize",
};

const OUTPUT_DISPLAY_NAMES = [
  "📤 输出区 · 图像",
  "├── 🔗 图片链接",
  "├── 🆔 任务ID",
  "└── 📋 响应信息",
];

function isRhNode(node) {
  return [node?.comfyClass, node?.type, node?.constructor?.comfyClass].includes(
    RH_NODE_TYPE,
  );
}

function setVisibleLabel(item, label) {
  if (!item || !label || typeof item !== "object") return;

  // Vue Nodes reads localized_name for connection slots.  The classic canvas
  // renderer reads label for widgets, so set both for either renderer.
  item.localized_name = label;
  item.label = label;
  item.display_name = label;
}

function hideLegacySeedControl(widget) {
  if (widget?.name !== "control_after_generate") return;

  // Older saved workflows can retain this automatically-created control.
  // It is intentionally disabled by the Python schema, so hide only that
  // legacy UI item without changing its saved value.
  widget.hidden = true;
  widget.options ??= {};
  widget.options.hidden = true;
}

function getInputDisplayName(slot) {
  return INPUT_DISPLAY_NAMES[slot?.name] ?? INPUT_DISPLAY_NAMES[slot?.widget?.name];
}

function attachDynamicInputLabelHook(node) {
  if (node.__rhDisplayNameInputHookAttached) return;
  node.__rhDisplayNameInputHookAttached = true;

  // A widget can be converted into a connection socket after the node is
  // created.  Label that newly-created socket as well.
  const originalOnInputAdded = node.onInputAdded;
  node.onInputAdded = function (slot, ...args) {
    const result = originalOnInputAdded?.call(this, slot, ...args);
    setVisibleLabel(slot, getInputDisplayName(slot));
    return result;
  };
}

function applyNodeDisplayNames(node) {
  if (!isRhNode(node)) return;

  attachDynamicInputLabelHook(node);

  for (const input of node.inputs ?? []) {
    setVisibleLabel(input, getInputDisplayName(input));
  }

  for (const widget of node.widgets ?? []) {
    setVisibleLabel(widget, INPUT_DISPLAY_NAMES[widget.name]);
    hideLegacySeedControl(widget);
  }

  for (const [index, output] of (node.outputs ?? []).entries()) {
    setVisibleLabel(output, OUTPUT_DISPLAY_NAMES[index]);
  }

  node.setDirtyCanvas?.(true, true);
}

function applyNodeDisplayNamesSoon(node) {
  applyNodeDisplayNames(node);

  // The Vue renderer may finish restoring widgets/slots just after a graph is
  // loaded.  Repeat once on the next event-loop turn to cover that path.
  setTimeout(() => applyNodeDisplayNames(node), 0);
}

function applyDefinitionDisplayNames(nodeData) {
  for (const groupName of ["required", "optional"]) {
    const group = nodeData.input?.[groupName];
    if (!group) continue;

    for (const [name, definition] of Object.entries(group)) {
      const config = Array.isArray(definition) ? definition[1] : undefined;
      const label = INPUT_DISPLAY_NAMES[name];
      if (config && label) {
        config.display_name = label;
        config.label = label;
      }
    }
  }

  if (Array.isArray(nodeData.output_name)) {
    nodeData.output_name = [...OUTPUT_DISPLAY_NAMES];
  }
}

function applyVueDefinitionDisplayNames(nodeDefs) {
  for (const nodeDef of nodeDefs ?? []) {
    if (nodeDef?.name !== RH_NODE_TYPE) continue;

    nodeDef.display_name = "🚀RH直连（兼容旧版）";

    const inputs = Array.isArray(nodeDef.inputs)
      ? nodeDef.inputs
      : Object.values(nodeDef.inputs ?? {});
    for (const input of inputs) {
      setVisibleLabel(input, INPUT_DISPLAY_NAMES[input?.name]);
    }

    const outputs = Array.isArray(nodeDef.outputs)
      ? nodeDef.outputs
      : Object.values(nodeDef.outputs ?? {});
    for (const [index, output] of outputs.entries()) {
      setVisibleLabel(output, OUTPUT_DISPLAY_NAMES[index]);
    }
  }
}

app.registerExtension({
  name: "fan.rh-node-display-names",

  // Vue Nodes has a separate definition-registration path.  Runtime labels
  // below are still the decisive step, but updating this data keeps the
  // definition metadata and canvas fallback aligned from the start.
  beforeRegisterVueAppNodeDefs(nodeDefs) {
    applyVueDefinitionDisplayNames(nodeDefs);
  },

  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== RH_NODE_TYPE) return;

    applyDefinitionDisplayNames(nodeData);

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = originalOnNodeCreated?.apply(this, args);
      applyNodeDisplayNamesSoon(this);
      return result;
    };

    const originalOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const result = originalOnConfigure?.apply(this, args);
      applyNodeDisplayNamesSoon(this);
      return result;
    };
  },

  nodeCreated(node) {
    applyNodeDisplayNamesSoon(node);
  },

  loadedGraphNode(node) {
    applyNodeDisplayNamesSoon(node);
  },
});
