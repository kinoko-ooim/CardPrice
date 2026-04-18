const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const DEFAULT_AI_API_URL = "https://api.openai.com/v1/chat/completions";
const DEFAULT_MODEL = "gpt-4.1-mini";

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function errorResponse(message, status, extra) {
  return jsonResponse(
    {
      error: message,
      ...(extra && typeof extra === "object" ? extra : {}),
    },
    status || 400,
  );
}

function sanitizeItem(raw, index) {
  const item = raw && typeof raw === "object" ? raw : {};
  const name = String(item.name || "").trim();
  const cardCode = String(item.cardCode || "").trim();
  const note = String(item.note || "").trim();
  const sourceText = String(item.sourceText || "").trim();

  let unitPrice = null;
  if (item.unitPrice !== null && item.unitPrice !== undefined && item.unitPrice !== "") {
    const parsedPrice = parseFloat(item.unitPrice);
    if (Number.isFinite(parsedPrice)) {
      unitPrice = Math.round(parsedPrice * 100) / 100;
    }
  }

  let qty = parseInt(item.qty, 10);
  if (!Number.isFinite(qty) || qty <= 0) {
    qty = 1;
  }

  return {
    id: "ai-" + index,
    name,
    cardCode,
    unitPrice,
    qty,
    note,
    sourceText,
    imageUrl: null,
    status: "未售出",
    source: "AI截图识别",
    sells: [],
    profit: null,
    cost: unitPrice === null ? 0 : Math.round(unitPrice * qty * 100) / 100,
  };
}

function stripCodeFence(text) {
  const raw = String(text || "").trim();
  if (!raw.startsWith("```")) {
    return raw;
  }
  return raw
    .replace(/^```[a-zA-Z0-9_-]*\s*/, "")
    .replace(/\s*```$/, "")
    .trim();
}

function parseAssistantJson(text) {
  const cleaned = stripCodeFence(text);
  const parsed = JSON.parse(cleaned);
  const items = Array.isArray(parsed && parsed.items) ? parsed.items : [];
  return items.map(sanitizeItem).filter(function(item) {
    return item.name;
  });
}

function buildMessages(imageDataUrl) {
  return [
    {
      role: "system",
      content: [
        {
          type: "text",
          text:
            "你是一个电商截图商品提取助手。请只提取截图里真实存在的商品行，按从上到下顺序输出。不要编造。不要解释。不要输出 Markdown。",
        },
      ],
    },
    {
      role: "user",
      content: [
        {
          type: "text",
          text:
            [
              "请识别这张商品列表截图，并输出严格 JSON。",
              "返回格式必须是 {\"items\":[...]}。",
              "每个 item 包含字段：name, cardCode, unitPrice, qty, note, sourceText。",
              "规则：",
              "1. name 是商品名，例如 猛雷鼓ex、皮卡丘。",
              "2. cardCode 是截图里显示的卡牌编号，尽量保持原样，例如 CSV7C-227/204、CSYC-005/011、S-P-208。",
              "3. unitPrice 只填数字，不要带 ¥。",
              "4. qty 如果截图有 x2 这种数量就填 2，没有就填 1。",
              "5. note 只放附加信息，例如 SR、无标记、PSA10、流通品相。",
              "6. sourceText 放这一条商品中你最关键的原始识别文本，便于人工复核。",
              "7. 如果某个字段无法判断，name 之外的字段可以留空字符串或 null，但不要瞎猜。",
              "8. 不要把评级卡编号当成 cardCode。",
              "9. 不要把价格拼进 name。",
            ].join("\n"),
        },
        {
          type: "image_url",
          image_url: {
            url: imageDataUrl,
            detail: "high",
          },
        },
      ],
    },
  ];
}

function buildRequestBody(model, imageDataUrl, useJsonSchema) {
  const body = {
    model: model || DEFAULT_MODEL,
    temperature: 0,
    messages: buildMessages(imageDataUrl),
  };

  if (useJsonSchema) {
    body.response_format = {
      type: "json_schema",
      json_schema: {
        name: "card_screenshot_extract",
        strict: true,
        schema: {
          type: "object",
          additionalProperties: false,
          properties: {
            items: {
              type: "array",
              items: {
                type: "object",
                additionalProperties: false,
                properties: {
                  name: { type: "string" },
                  cardCode: { type: "string" },
                  unitPrice: { anyOf: [{ type: "number" }, { type: "null" }] },
                  qty: { type: "integer" },
                  note: { type: "string" },
                  sourceText: { type: "string" },
                },
                required: ["name", "cardCode", "unitPrice", "qty", "note", "sourceText"],
              },
            },
          },
          required: ["items"],
        },
      },
    };
  }

  return body;
}

function extractAssistantText(data) {
  if (!data || !Array.isArray(data.choices) || data.choices.length === 0) {
    return "";
  }
  const message = data.choices[0] && data.choices[0].message ? data.choices[0].message : null;
  if (!message) {
    return "";
  }
  if (typeof message.content === "string") {
    return message.content;
  }
  if (Array.isArray(message.content)) {
    for (const part of message.content) {
      if (part && typeof part.text === "string" && part.text.trim()) {
        return part.text;
      }
    }
  }
  return "";
}

function readProviderConfig(requestedModel) {
  const apiUrl = (Deno.env.get("AI_API_URL") || Deno.env.get("OPENAI_API_URL") || DEFAULT_AI_API_URL).trim();
  const apiKey = (Deno.env.get("AI_API_KEY") || Deno.env.get("OPENAI_API_KEY") || "").trim();
  const model = String(requestedModel || Deno.env.get("AI_MODEL") || DEFAULT_MODEL).trim() || DEFAULT_MODEL;
  const authHeader = (Deno.env.get("AI_AUTH_HEADER") || "Authorization").trim() || "Authorization";
  const authScheme = (Deno.env.get("AI_AUTH_SCHEME") || "Bearer").trim();
  const useJsonSchema = String(Deno.env.get("AI_USE_JSON_SCHEMA") || "true").trim().toLowerCase() !== "false";
  return {
    apiUrl,
    apiKey,
    model,
    authHeader,
    authScheme,
    useJsonSchema,
  };
}

async function callProvider(config, imageDataUrl) {
  const headers = {
    "Content-Type": "application/json",
  };
  headers[config.authHeader] = config.authScheme
    ? config.authScheme + " " + config.apiKey
    : config.apiKey;

  const response = await fetch(config.apiUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(buildRequestBody(config.model, imageDataUrl, config.useJsonSchema)),
  });

  const data = await response.json();
  if (!response.ok) {
    const message =
      data && data.error && data.error.message
        ? data.error.message
        : "AI 提供方请求失败 (" + response.status + ")";
    throw new Error(message);
  }
  return data;
}

Deno.serve(async function(req) {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return errorResponse("只支持 POST 请求", 405);
  }

  try {
    const body = await req.json();
    const imageDataUrl = String((body && body.imageDataUrl) || "").trim();
    const providerConfig = readProviderConfig(body && body.model);

    if (!providerConfig.apiKey) {
      return errorResponse("Supabase Edge Function 未配置 AI_API_KEY 或 OPENAI_API_KEY", 500);
    }
    if (!providerConfig.apiUrl) {
      return errorResponse("Supabase Edge Function 未配置 AI_API_URL", 500);
    }

    if (!imageDataUrl) {
      return errorResponse("缺少 imageDataUrl", 400);
    }
    if (!/^data:image\//.test(imageDataUrl)) {
      return errorResponse("目前仅支持 data URL 图片输入", 400);
    }

    const data = await callProvider(providerConfig, imageDataUrl);
    const assistantText = extractAssistantText(data);
    if (!assistantText) {
      return errorResponse("AI 没有返回可解析内容", 502, { raw: data });
    }

    let items = [];
    try {
      items = parseAssistantJson(assistantText);
    } catch (parseError) {
      return errorResponse("AI 返回内容无法解析为 JSON", 502, {
        rawText: assistantText,
        detail: String(parseError && parseError.message ? parseError.message : parseError),
      });
    }

    return jsonResponse({
      items,
      model: providerConfig.model,
      apiUrl: providerConfig.apiUrl,
      rawText: assistantText,
    });
  } catch (error) {
    console.error("card-screenshot-extract-v1 failed", error);
    return errorResponse(error && error.message ? error.message : "截图 AI 识别失败", 500);
  }
});
