# 梓辰 Skills

把反复使用的方法整理为可以安装、阅读和执行的 Agent Skills。

已发布的 Skill 都提供完整指令、使用说明和单独的许可证，可以阅读逻辑后安装使用。

公开仓库：[zichen-ai/zichen-skills](https://github.com/zichen-ai/zichen-skills)。

## 从哪里开始

- 想使用 Skill：在下面的目录选择任务，阅读对应的使用说明、依赖和边界。
- 想反馈问题：通过仓库 Issues 提供脱敏后的输入、预期行为和实际行为，请勿提交真实客户资料或密钥。
- 维护仓库：[发布规范](docs/publishing-standard.md)、[发布操作](docs/publishing-guide.md)、[版本与验证](docs/verification.md)。

## 已发布 Skills

- **[决策型营销 decision-marketing](skills/decision-marketing/README.md)**：先了解业务和真实需求，提炼客户为什么购买、为什么选择你，再把自我营销自然写进内容。关键案例缺失时主动追问，材料足够后交稿。[阅读完整 MD](skills/decision-marketing/SKILL.md)。

版本与验证范围见 [catalog.json](catalog.json)。

## 安装与使用

最简单的方式是下载 [决策型营销 SKILL.md](skills/decision-marketing/SKILL.md)，把文件发给能读取附件的 AI，再发送：

> 请完整读取附件并使用决策型营销技能。若能持久安装到当前工具实际读取的技能目录，请直接安装并核对，已有同名内容不同时先保留并告诉我；否则在本次对话使用，并说明使用范围。先根据我的资料判断真正的问题，缺少关键背景或案例时问我，信息足够后完成任务。

随后提供产品介绍、原稿或具体问题。文件直传无需运行安装命令；仅在当前对话使用时，换新对话重新上传。完整步骤见[客户使用说明](skills/decision-marketing/README.md)。

也可以使用下面的命令安装到 Codex：

在已安装 Node.js 22.20+、npm、Git 和 Codex 的电脑上运行：

```sh
npx -y skills@1.9.0 add zichen-ai/zichen-skills --skill decision-marketing -g -a codex -y
```

Claude Code 用户将 `codex` 换成 `claude-code`。详细步骤与调用示例见[决策型营销使用说明](skills/decision-marketing/README.md)。安装需要支持 Agent Skills 的 AI 工具；涉及外部服务的 Skill 还需要使用者自行配置对应账号或凭据。安装与运行能力以每个 Skill 的说明和测试记录为准。

每个 Skill 提供适用情境、输入要求、使用示例、成果说明和主要限制。不同模型和工具可能得到不同结果。

## 仓库结构

```text
skills/            已确认公开的 Skill 包
catalog.json       已发布目录、版本与验证说明
docs/              发布与维护规范
templates/         编写指导（不会被识别为可安装 Skill）
tools/             检查、发布计划和上传程序
publish.cmd        Windows 一键上传入口
.github/           自动检查和反馈模板
```

## 许可

本仓库自有的发布工具、规范文档与模板按 [MIT 许可证](LICENSE) 提供。`skills/` 内每个 Skill 必须单独附带许可证；收录前逐项确认原创内容、第三方材料与允许的使用方式。根目录许可证不自动覆盖未来收录的 Skill 或第三方材料。

## 标准参考

- [Agent Skills 格式规范](https://agentskills.io/specification)
- [Skills 安装工具](https://github.com/vercel-labs/skills)

