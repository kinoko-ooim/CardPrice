`card-image-lookup-v2` 是给网页“获取图片”按钮用的 Supabase Edge Function。

部署方式：

1. 在 Supabase Dashboard 打开 `Edge Functions`
2. 新建函数，名字填 `card-image-lookup-v2`
3. 把 [index.ts](/Users/chenyuanxi/Desktop/卡价/supabase/functions/card-image-lookup-v2/index.ts) 的内容完整粘进去
4. 保存并部署

部署完成后，网页里的“获取图片”会优先调用这个云函数：
- 旧编号先尝试 `tcg.mik.moe`
- 新编号或旧站无图时，回退到 `TCG Collector`

如果后面你本机装了 `supabase` CLI，也可以改成命令行部署。

---

`card-screenshot-extract-v1` 是给网页“截图识别新增 -> AI识别”按钮用的 Supabase Edge Function。

部署方式：

1. 在 Supabase Dashboard 打开 `Edge Functions`
2. 新建函数，名字填 `card-screenshot-extract-v1`
3. 把 [index.ts](/Users/chenyuanxi/Desktop/卡价/supabase/functions/card-screenshot-extract-v1/index.ts) 的内容完整粘进去
4. 在项目的 `Edge Functions -> Secrets` 里添加 AI 提供方配置。默认支持两种方式：
   `OPENAI_API_KEY=你的 OpenAI API Key`
   或者
   `AI_API_KEY=第三方平台 Key`
5. 如果是第三方 OpenAI 兼容平台，再额外加：
   `AI_API_URL=该平台的基地址或 chat completions 接口地址`
   `AI_MODEL=你要调用的模型名`
6. 如果第三方平台不支持 `json_schema` 结构化输出，再额外加：
   `AI_USE_JSON_SCHEMA=false`
7. 在这个函数的设置里关闭 `Verify JWT`
8. 保存并部署

部署完成后，网页里的“AI识别”会把截图发给这个云函数，返回结构化的商品记录草稿，再由你确认导入。
