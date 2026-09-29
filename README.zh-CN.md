# Design Workflow

[English](README.md) | **简体中文**

**一句话换外观，一句话生成场景。**

向你的 AI 编程助手描述需求。Design Workflow 为机器人外观（`.skin`）和环境场景（`.map`）提供生成规则、文件标准与校验工具。

## 看看可以做什么

### 机器人外观 · `.skin`

通过一个仅用于显示的文件替换整机外观。3D 打印文件单独交付。

| [银甲卫士](library/skins/mecha-tripo-v3.skin) | [拉斐尔忍者龟](library/skins/raphael-turtle-v1.skin) | [暖沙游侠](library/skins/warm-sand-ranger-integrated-v2.skin) |
|---|---|---|
| [![银甲卫士](docs/assets/examples/mecha-tripo-v3.png)](library/skins/mecha-tripo-v3.skin) | [![拉斐尔忍者龟](docs/assets/examples/raphael-turtle-v1.png)](library/skins/raphael-turtle-v1.skin) | [![暖沙游侠](docs/assets/examples/warm-sand-ranger-integrated-v2.png)](library/skins/warm-sand-ranger-integrated-v2.skin) |

### 环境与挑战 · `.map`

加载包含地形、道具和默认机器人的场景。缩略图只展示环境，不包含机器人。

| [卧室](library/maps/bedroom.map) | [足球场](library/maps/soccer.map) | [公园泵道](library/maps/park-pump-track.map) |
|---|---|---|
| [![卧室](docs/assets/examples/bedroom.png)](library/maps/bedroom.map) | [![足球场](docs/assets/examples/soccer.png)](library/maps/soccer.map) | [![公园泵道](docs/assets/examples/park-pump-track.png)](library/maps/park-pump-track.map) |

[浏览全部外观](library/skins/README.md) · [浏览全部场景](library/maps/README.md) · [查看工作流](docs/workflow.md)

案例图片来自已发布文件内嵌的实际缩略图。这里的图片是文档展示副本；每个 `.skin`、`.map` 都包含自身所需资源。

## 一句话，两条工作流

完成[项目安装](#快速开始)后，在能够读取文件、执行命令的 AI 编程助手中打开本仓库。让助手先阅读 [AGENTS.md](AGENTS.md)，再描述你想要的外观或场景。

| 一句话换外观 | 一句话生成场景 |
|---|---|
| **示例指令：**“给跳跳换上暖沙游侠外观，机身和肢体采用协调配色，导出为 .skin。” | **示例指令：**“生成一个有起伏路面、树木和长椅的公园泵道，放入可直接使用的跳跳，导出为 .map。” |
| 描述需求 → 确认设计 → 生成 → 校验 | 描述需求 → 构建场景 → 预览 → 校验 |
| **交付结果：**用于显示的整机 `.skin`，可导入兼容的查看器或仿真器。 | **交付结果：**包含环境资源、默认机器人及出生位置的独立 `.map`。 |
| [![暖沙游侠示例](docs/assets/examples/warm-sand-ranger-integrated-v2.png)](library/skins/warm-sand-ranger-integrated-v2.skin) | [![公园泵道示例](docs/assets/examples/park-pump-track.png)](library/maps/park-pump-track.map) |
| [下载示例 .skin](library/skins/warm-sand-ranger-integrated-v2.skin) | [下载示例 .map](library/maps/park-pump-track.map) |

一句话是工作流的入口。助手会检查可用工具和输入，必要时请你选择设计方案，再生成并校验文件。新造型可能需要外部建模工具或你提供的模型，不能保证任意需求都能一步自动完成。上图展示已有案例，不代表每次输入示例指令都会得到完全相同的结果。

仓库包含 Python 参考工具、文件标准、带版本约束的跳跳基准，以及完整的 **16 个外观和 13 个场景**。上面展示了部分案例，更多操作见[详细工作流](docs/workflow.md)。

## 快速开始

需要 Python 3.10 或更新版本。下载案例文件和机器人网格需要安装 Git LFS。

```sh
git lfs install
git clone https://github.com/KingKongRobotics/kingkong-design.git
cd kingkong-design
git lfs pull
python -m pip install -e ".[sim,dev]"
python scripts/shellflow.py --help
```

文件校验和首次场景导出方法见[快速入门指南](docs/quickstart.md)。详细技术文档目前以英文为主。

## 工具能做什么

- 读取、校验、导入和重新打包带版本信息的 `.skin`、`.map` 文件。
- 导出仅用于显示的整机 `.skin`，将场景描述编译为 `.map`。
- 检查文件结构、资源清单、哈希和机器人兼容性，并可通过原生 MuJoCo 加载模型。
- 为实体外壳工作流记录证据和交付物。几何生成、打印验收与实物试装需要分别完成。

自动检查通过不代表视觉效果正确，仍需查看实际外观和场景。原生 MuJoCo 编译检查模型能否加载，不代表修改后的外壳通过了运动表现或实物安装验证。详见[工程与验收](docs/engineering-and-acceptance.md)。

## 仓库目录

- `src/`：Python 工具包与 MuJoCo 场景编译器。
- `scripts/`：命令行入口及资源导入、导出工具。
- `schemas/`：文件清单的 JSON Schema 定义。
- `robots/jumper/`：带版本约束的整机基准与配置。
- `library/skins/`、`library/maps/`：完整案例文件及索引。
- `examples/`：场景源文件示例。
- `docs/`：文件协议、工作流、架构和许可文档。

从[文档导航](docs/index.md)开始阅读。文件布局和兼容性规则见[资源文件协议](docs/content-packages.md)。

## 许可证

维护者拥有权利的项目内容采用 Apache-2.0。详见 [LICENSE](LICENSE)、[NOTICE](NOTICE) 和[许可说明](docs/licensing.md)。第三方内容保留其各自的许可条款；使用本工具生成的文件不会自动继承本仓库许可证。
