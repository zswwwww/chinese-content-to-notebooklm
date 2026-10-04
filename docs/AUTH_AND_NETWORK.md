# 登录和网络

本项目使用固定版本的上游 `nlm`。先在安装环境中执行 `nlm login --storage protected`，再用 `nlm notebook list --json` 或 `chinese-notebooklm doctor --check-login` 验证。无需提供OpenAI API key；总结由你登录的NotebookLM账户生成。

## 普通浏览器能访问，专用窗口却不能访问

专用浏览器配置不一定包含日常浏览器扩展。若平时依赖扩展访问Google，后台Python工具也未必有相同网络出口。应检查代理和真实认证请求，不能仅凭未登录页面的地区提示认定登录失效。

`config.local.json` 的 `notebooklm_proxy` 控制本项目发往NotebookLM的请求；`bilibili_proxy`独立控制B站。若直接执行 `nlm` 登录命令，也要给这个命令设置代理环境。

PowerShell示例，端口应替换成自己代理软件提供的HTTP代理端口：

```powershell
$env:HTTP_PROXY = 'http://127.0.0.1:<端口>'
$env:HTTPS_PROXY = $env:HTTP_PROXY
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
nlm login --storage protected
```

本项目不修改系统代理、不切换节点、不读取扩展的密钥。

## 使用自己浏览器的登录文件

用户无法在专用窗口完成登录时，可以按上游的手动登录方式，在自己已经登录的NotebookLM页面打开开发者工具：Network → 页面中一个发往 `notebook.google.com` 的 `batchexecute` 请求 → Request headers → `cookie`。`cookie`是请求头名称，没有固定的值前缀，不能按几个点或某个固定字符串去寻找。

把完整Cookie请求头的值保存到仓库之外的本地文件，然后由用户执行：

```text
nlm login --manual --file <本地文件路径> --storage protected
nlm notebook list --json
```

不要粘贴Cookie到聊天、Issue或README；不要把导出的登录文件加入Git。登录成功后，按自己的文件管理方式移除临时明文副本。认证资料始终由上游管理，本项目不读取或导出它们。

网络超时、地区限制与认证过期是不同情况。先检查错误和网络，只有确认认证不可用时才重新登录。多个账户用 `--profile <名称>`；不要随意切换默认账户。
