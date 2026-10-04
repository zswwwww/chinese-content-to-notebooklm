# 处理进度与恢复

每个来源的输出目录名取决于规范化来源、目标笔记本与profile。本地文件还加入内容哈希。同一个输出根目录下相同来源重跑会保留进度；换目录或改目标会产生新的状态记录。

`result.json` 保存提取结果、stage及已返回的NotebookLM ID：

- `extracted`：已保存正文。
- `creating`：准备创建笔记本；若没有notebook_id，请先核对远端。
- `notebook_created`：已保存笔记本ID。
- `uploading`：准备上传来源；若没有source_id，请先核对远端。
- `uploaded`：已保存来源ID，可以继续等待索引和查询。
- `complete`：总结已保存。更换问题会重新查询同一来源。

## 结果不确定时

网络中断可能发生在远端已成功、客户端尚未收到ID时。因此程序会停在不确定状态，避免自动重复请求。

1. 用 `nlm notebook list --json` 或NotebookLM网页核对笔记本；已有目标时取得真实ID。
2. 备份本地 `result.json`，把已确认的 `notebook_id` 和对应 `notebook_url` 补入记录，stage改为 `notebook_created`。只有确定原创建请求没有成功时，才改回 `extracted`。
3. 上传不确定时核对目标笔记本来源列表：`nlm source list <笔记本ID> --json`。已有来源时补入 `source_id` 并设stage为 `uploaded`。只有确定没有成功上传，才改回 `notebook_created`。
4. 保留输出根目录，用原参数重跑。若来源仍在处理，后续等待失败会保留ID，可稍后继续。

修改记录前应确认ID、账户和来源对应；不要用占位ID，也不要删除远端资料来掩盖状态不确定。来源锁只协调同一个输出目录，无法阻止不同目录同时创建相同内容。
