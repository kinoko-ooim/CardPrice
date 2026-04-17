const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const R_JINA_PREFIX = "https://r.jina.ai/http://";
const TCGCOLLECTOR_SETS_URL =
  "https://www.tcgcollector.com/sets/jp?cardCountMode=anyCardVariant&releaseDateOrder=newToOld&displayAs=images";
const TCGCOLLECTOR_SEARCH_URL =
  "https://www.tcgcollector.com/cards/jp?cardSource=inCardVariant&releaseDateOrder=newToOld&displayAs=images&cardSearch={query}";
const TCG_MIK_URL = "https://tcg.mik.moe/static/img/{set_code}/{card_num}.png";
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function errorResponse(message, status) {
  return jsonResponse({ error: message }, status || 400);
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": USER_AGENT },
  });
  if (!response.ok) {
    throw new Error(`请求失败 (${response.status})`);
  }
  return await response.text();
}

async function urlExists(url) {
  try {
    const response = await fetch(url, {
      headers: { "User-Agent": USER_AGENT },
    });
    return response.ok;
  } catch (_error) {
    return false;
  }
}

function rJinaUrl(url) {
  return `${R_JINA_PREFIX}${url}`;
}

function parseCardCode(raw) {
  const cleaned = String(raw || "").trim().replace(/\s+/g, "").replace(/[–—_]/g, "-");
  let match = cleaned.match(/^(.+)-(\d{1,3})(?:\/([A-Za-z0-9.-]+))?$/);
  if (!match) {
    match = cleaned.match(/^([A-Za-z0-9.-]+?)(\d{2,3})(?:\/([A-Za-z0-9.-]+))?$/);
  }
  if (!match) {
    throw new Error("编号格式无法识别，请使用类似 CSM2bC-034 或 M1L-089/063 的格式。");
  }
  const setCode = match[1];
  const cardNum = String(match[2]).padStart(3, "0");
  const denominator = match[3] || "";
  const cardNumber = denominator ? `${cardNum}/${denominator}` : cardNum;
  return {
    raw,
    setCode,
    cardNum,
    denominator,
    cardNumber,
    canonical: `${setCode}-${cardNumber}`,
  };
}

async function loadSetCodeMap() {
  const markdown = await fetchText(rJinaUrl(TCGCOLLECTOR_SETS_URL));
  const pattern = /\[([^\[\]\n]+?)\]\(https:\/\/www\.tcgcollector\.com\/sets\/\d+\/[^\)]+\)([A-Za-z0-9.-]+)/g;
  const mapping = {};
  let match = null;
  while ((match = pattern.exec(markdown)) !== null) {
    const name = (match[1] || "").trim();
    const code = (match[2] || "").trim();
    if (code && !mapping[code]) {
      mapping[code] = name;
    }
  }
  if (Object.keys(mapping).length === 0) {
    throw new Error("未能从 TCG Collector 解析出日版卡包列表。");
  }
  return mapping;
}

async function searchTcgCollector(code, setName) {
  const query = encodeURIComponent(code.cardNumber);
  const url = TCGCOLLECTOR_SEARCH_URL.replace("{query}", query);
  const markdown = await fetchText(rJinaUrl(url));
  const entryPattern =
    /\[\!\[Image \d+: ([^\]]+)\]\((https:\/\/static\.tcgcollector\.com\/content\/images\/[^\)]+)\)\s+!\[Image \d+: ([^\]]+)\]\([^\)]*\)\s+(\d+\/\d+).*?\]\((https:\/\/www\.tcgcollector\.com\/cards\/\d+\/[^ \)]+)/gs;

  const matches = [];
  let match = null;
  while ((match = entryPattern.exec(markdown)) !== null) {
    if ((match[4] || "").trim() !== code.cardNumber) continue;
    matches.push({
      code: code.canonical,
      source: "tcgcollector",
      title: (match[1] || "").trim(),
      imageUrl: (match[2] || "").trim(),
      pageUrl: (match[5] || "").trim(),
      setName: (match[3] || "").trim(),
    });
  }

  if (matches.length === 0) {
    throw new Error(`没有在 TCG Collector 中找到 ${code.cardNumber} 的结果。`);
  }

  if (setName) {
    for (const item of matches) {
      if (item.setName === setName) return item;
    }
  }

  if (matches.length === 1) {
    return matches[0];
  }

  const available = matches
    .slice(0, 5)
    .map((item) => `${item.setName}: ${item.title}`)
    .join(" / ");
  throw new Error(`找到了多个同编号结果，但没法唯一匹配 ${code.setCode}。候选：${available}`);
}

async function lookupCardImage(rawCode) {
  const code = parseCardCode(rawCode);
  const tcgMikUrl = TCG_MIK_URL
    .replace("{set_code}", code.setCode)
    .replace("{card_num}", code.cardNum);

  if (await urlExists(tcgMikUrl)) {
    return {
      code: code.canonical,
      source: "tcg.mik.moe",
      title: code.canonical,
      imageUrl: tcgMikUrl,
      pageUrl: "",
      setName: "",
    };
  }

  if (!code.denominator) {
    throw new Error(`${code.canonical} 在 tcg.mik.moe 上不存在，且编号里没有总卡数，无法继续精确匹配。`);
  }

  const setNameMap = await loadSetCodeMap();
  const setName = setNameMap[code.setCode] || "";
  return await searchTcgCollector(code, setName);
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (request.method !== "POST") {
    return errorResponse("仅支持 POST", 405);
  }

  try {
    const body = await request.json();
    const code = String((body && body.code) || "").trim();
    if (!code) {
      return errorResponse("缺少卡牌编号 code", 400);
    }
    const result = await lookupCardImage(code);
    return jsonResponse(result, 200);
  } catch (error) {
    const message = error && error.message ? error.message : "查图失败";
    return errorResponse(message, 500);
  }
});
