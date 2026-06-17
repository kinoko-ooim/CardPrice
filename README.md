# 卡价

这是一个以静态网页为主的卡牌库存与售出管理项目。

当前为了兼容现有页面里的相对路径，网页入口文件和会被浏览器直接读取的资源仍然放在仓库根目录；其余脚本、说明和数据已经按用途拆分到子目录里，后续维护会轻松很多。

## 目录说明

```text
卡价/
├── index.html              # 主页面入口
├── tab0754.js              # 0754 售出记录组件
├── clear_cache.html        # 清理浏览器本地缓存
├── 卡价.xlsx               # 页面会直接读取的 Excel 文件
├── cardimg/                # 本地图像资源
├── supabase/               # Supabase Edge Functions
├── supabase_setup.sql      # Supabase 初始化脚本
├── scripts/                # 辅助脚本
├── docs/                   # 项目说明和参考资料
└── data/                   # 原始数据、备份和导出文件
```

## 常用位置

- 页面主入口：`index.html`
- 图片目录：`cardimg/`
- Supabase 函数说明：`supabase/functions/README.md`
- 图片查找脚本：`scripts/card_image_lookup.py`
- 历史数据和备份：`data/`

## 页面功能

- “截图识别新增”支持选择图片，也支持在弹窗打开后直接粘贴剪贴板图片，再用 AI 识别或本地 OCR 识别。
- 卡牌编辑和新增时可以勾选 `PSA10` 标识；卡牌名称旁会显示 `PSA10` 标签。
- 表格“单价”下方会显示单价与参考价的差值：普通卡对比“流通品价”，勾选 `PSA10` 的卡对比“PSA10价”。
- CSV 导出会包含“是否PSA10”列，方便备份和二次整理。
- 页面直接用 `file://` 打开时，如果浏览器禁止 `sessionStorage`，密码验证会自动退回到当前页面内存状态，不影响进入后台。
- 密码入口带有独立于 React 的兜底表单：即使 React/Babel/CDN 脚本加载失败，也会保留可输入的密码框，避免只显示背景空白页。
- “截图识别新增 -> AI识别”兼容两种接入方式：如果在弹窗里的“AI配置”保存了 OpenAI 兼容直连 API，会优先直连识别；没有直连配置时，会继续使用 Supabase Edge Function `card-screenshot-extract-v1`。
- 直连 API 配置保存在当前浏览器 `localStorage`，默认示例为 `http://43.155.156.14:8080/v1/chat/completions`、模型 `gpt-5.5`、`AI_USE_JSON_SCHEMA=false`。如果页面通过 `file://` 打开，API 网关需要允许浏览器 CORS（常见为 `Origin: null`），否则页面会提示直连被拦截并尝试 Supabase 兜底。
- “AI配置”里的 API Key 输入框默认隐藏，保存状态只显示打码摘要；配置弹窗提供“测试连接”按钮，会用轻量文本请求检查直连 API 是否可用，并显示成功、401/403 或 CORS 拦截等结果。
- Supabase 模式仍然需要在 Edge Function Secrets 里配置 `AI_API_KEY`/`AI_MODEL` 等变量；如果 AI 提供方返回 401/403/429 等错误，页面会在弹窗里保留失败原因，方便检查 API Key、额度、模型权限和接口地址。
- 截图识别结果自动配图时，日版编号会按“卡包代号 + 包内编号”精确匹配：例如 `SV2P-075/071` 会先定位 `SV2P -> Snow Hazard`，再只接受 `Snow Hazard` 里的 `075/071`，避免同编号跨卡包误配图；常见 SV 系列代号会用内置对照表兜底，减少 TCG Collector 卡包列表结构变化带来的漏配。

## 常用命令

```bash
cd /Users/chenyuanxi/Desktop/卡价
python3 scripts/card_image_lookup.py M1L-089/063 --download
python3 scripts/migrate.py
python3 scripts/migrate_cardcode.py
python3 scripts/update_jhs_prices.py --source supabase --dry-run
```

## 集换社价格每日更新

`scripts/update_jhs_prices.py` 会读取“卡价管理”里状态为“未售出”且带有 `cardCode` 的商品，尝试从本机集换社 App 的只读缓存或可见 UI 中识别“流通品价”和“PSA10价”，然后写回 `jhsRawPrice`、`jhsPsa10Price`、`jhsPriceUpdatedAt` 和 `jhsPriceNote`。

如果同一个编号在宝可梦简中、日文、英文里分别对应不同卡，可以在商品编辑弹窗的“集换社参考价”里设置 `集换社搜索编号` 和 `集换社游戏语言`。每日更新会优先使用这两个字段；未设置时才自动判断。

这个脚本不会解密集换社的 `raw_data`，也不会复制登录态；如果缓存里没有明文价格，会保留原价并记录未更新原因。

Supabase 读取商品列表时会对短暂的 TLS/网络失败进行重试，避免代理或网络节点偶发抖动时直接中断；如果多次重试后仍失败，脚本会退出并保留错误栈，切换网络或代理后可重新运行。

## 维护约定

- 如果文件会被网页通过 `fetch('./文件名')` 直接读取，优先留在根目录。
- 辅助脚本统一放到 `scripts/`。
- 说明文档统一放到 `docs/`。
- 备份、原始导出、Numbers 中间文件统一放到 `data/`。
