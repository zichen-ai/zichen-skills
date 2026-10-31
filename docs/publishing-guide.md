# 发布操作

## 第一次配置

需要 Git 和 Python 3.10 或更新版本；安装验证另需 Node.js，版本要求以 Skills 安装工具的当前说明为准。发布工具仅用 Python 标准库，不安装额外 Python 依赖。

创建远端公开仓库后，在独立的本地仓库配置 `origin`。完成 GitHub 身份验证；认证信息交给 Git 的凭据管理器，不写进仓库、脚本或聊天。

`python tools/release.py configure --repository <owner>/zichen-skills` 将最终仓库地址写入被忽略的 `.local/config.json`。程序核对 `origin` 和这个地址完全一致；只允许 HTTPS GitHub 远端。用户名变化后更新配置和远端，再重新准备发布计划。

## 确认一个 Skill 后

1. 从原件制作公开副本，按发布规范清理依赖、资料和许可；完整保留用户确认的行为。
2. 完成行为与留出/回归测试，原始输入、答案和输出保留在仓库外。公开目录只写准确的验证摘要。
3. 把已确认副本放到 `skills/<name>/`，更新 `catalog.json`、仓库首页与包内 README。
4. 运行 `python tools/release.py check`。自动检查只代表结构和有限敏感模式扫描；它不能替代人工审阅或行为验证。
5. 用明确文件清单生成计划，例如：

```text
python tools/release.py plan --files README.md catalog.json skills/example/SKILL.md skills/example/README.md skills/example/LICENSE --message "Publish example skill"
```

`example` 是格式示例，并非已存在的 Skill。资源文件逐个列入清单，不传整个本地 skills 目录。计划保存在 `.local/publish-plan.json`，列出目标、分支、变化类型和文件 SHA-256。

6. 共同审阅实际文件和差异。梓辰确认这个范围后，维护者记录确认：

```text
python tools/release.py approve --note "记录本次用户确认的具体范围"
```

记录确认属于维护者动作，程序本身不能证明用户已经同意。不得把用户仅仅讨论内容当作发布授权。

7. 双击根目录 `publish.cmd`，或运行 `python tools/release.py publish`。程序重新核验文件哈希、目标远端、分支、远端版本和暂存区，再逐个暂存、提交、推送，核对远端提交成功后报告完成。

## 一键上传的边界

一键入口只消费已确认的计划。没有计划、计划未确认、文件后来修改、出现清单之外的改动、暂存区有内容、分支或远端变化时停止。它不会自动收录 Skill、强制推送、创建版本 tag/Release，也不发送消息。

网络中断可能发生在提交之后：计划会记录已生成的提交；修复网络后重新运行入口，可以继续推送同一个提交。若本地或远端出现其他提交，先检查差异并重新制定计划，不自动合并或覆盖。

## 发布后验证

在隔离目录和临时用户环境中安装具体 Skill，确认安装器可发现包；对安装后的 `SKILL.md`、参考资料、脚本与资源逐个比较；再运行代表性任务。记录安装器版本与验证日期，避免修改维护者正在使用的同名 Skill。

发布工具本身的测试命令：`python -m unittest discover -s tools/tests -v`。

