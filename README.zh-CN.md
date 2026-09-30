# Design Workflow

[English](README.md) | **简体中文**

为 **跳跳** 这款 22 自由度螃蟹机器人设计外观并创建场景。[查看硬件 →](https://github.com/KingKongRobotics/jumper/blob/main/docs/HARDWARE.zh.md)

在 AI 编程助手中打开本仓库，用一句话描述你想要的内容。下面的指南会为助手提供相应的工作流。

> 🦀 **免费获得跳跳！** [了解如何领取 →](https://beunlimited.me/zh/events/crab-robot-challenge-2026)

## 一句话，设计外观

> 为跳跳设计暖沙游侠外观，协调机身和肢体配色，然后导出 `.skin`。

| | | |
|:-:|:-:|:-:|
| ![暖沙游侠外观](docs/assets/examples/warm-sand-ranger-integrated-v2.png) | ![银甲外观](docs/assets/examples/mecha-tripo-v3.png) | ![拉斐尔忍者龟外观](docs/assets/examples/raphael-turtle-v1.png) |
| [**暖沙游侠**](library/skins/warm-sand-ranger-integrated-v2.skin) | [**银甲**](library/skins/mecha-tripo-v3.skin) | [**拉斐尔忍者龟**](library/skins/raphael-turtle-v1.skin) |

[浏览全部外观](library/skins/README.md)

## 一句话，生成场景

> 为跳跳创建一个有起伏地形、树木和长椅的公园泵道场景，然后导出 `.map`。

| | | |
|:-:|:-:|:-:|
| ![公园泵道场景](docs/assets/examples/park-pump-track.png) | ![卧室场景](docs/assets/examples/bedroom.png) | ![足球场景](docs/assets/examples/soccer.png) |
| [**公园泵道**](library/maps/park-pump-track.map) | [**卧室**](library/maps/bedroom.map) | [**足球场**](library/maps/soccer.map) |

[浏览全部场景](library/maps/README.md)

这些是已有的外观和场景文件示例。必要时助手会请你选择设计，并校验文件结构和兼容性；新几何可能需要外部建模工具或你提供模型，不能保证任意设计都能一步自动完成，自动检查也不能替代视觉检查、控制器评估或实体试装。

## 相关项目与指南

| 资源 | 用途 |
|---|---|
| [跳跳](https://github.com/KingKongRobotics/jumper) | 外观设计、动作训练与场景生成的统一入口。 |
| [快速开始](docs/quickstart.md) | 安装工具、校验示例并导出场景。 |
| [工作流](docs/workflow.md) | 外观、环境和实体外壳工作流。 |
| [资源文件协议](docs/content-packages.md) | `.skin` 和 `.map` 格式、清单与校验。 |
| [工程与验收](docs/engineering-and-acceptance.md) | 数字证据、视觉检查、打印和实体试装边界。 |

训练和控制器工作独立于本仓库。第三方组件及导入的场景代码保留各自的声明和许可条款，详见 [NOTICE](NOTICE) 和[许可说明](docs/licensing.md)。

## 许可证

Copyright 2026 KingKong Robotics.

维护者拥有权利的项目内容采用 Apache-2.0。详见 [LICENSE](LICENSE)、[NOTICE](NOTICE)
和[许可说明](docs/licensing.md)。第三方内容保留其各自的许可条款；使用本工具生成的文件不会自动继承本仓库许可证。
