# Changelog

## [0.6.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.5.0...v0.6.0) (2026-06-08)


### Features

* add houdini-material-library skill with 12 tools ([332df88](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/332df8838f68a85b0debe84d4426c07edfe88e87))


### Bug Fixes

* ruff format and dcc-mcp-core compatibility version for material-library skill ([81df931](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/81df9312cdd3b98f7d01637133fb92019dbf5b88))

## [0.5.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.4.1...v0.5.0) (2026-06-07)


### Features

* add houdini-texture-bake skill with 5 typed bake tools ([78c1fc0](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/78c1fc0ca239fedcd383fc31abb499e5858ebb86))


### Bug Fixes

* **ci:** apply ruff formatting to install_dcc_mcp_cli.py ([9817d70](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/9817d704910d2075def7f7572373bc09d60876f3))
* **ci:** fallback through recent releases when latest lacks CLI binary ([66c09d6](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/66c09d68ead7950656e9ef04dfca15e1c4ed2bf8))
* **ci:** fix import sorting in test_agent_instruction_files.py ([279360d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/279360d4e20aef92d47ac146dc1ba1f05961f492))
* lint errors in houdini-texture-bake skill scripts ([bb5d646](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/bb5d64677a812d6d69aeacd5f7751ad0e2dda0b2))
* review feedback — rebase, remove redundant baker_available, add tests ([38ac832](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/38ac8323e63dd2316406cb90c645aa8224949811))

## [0.4.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.4.0...v0.4.1) (2026-06-07)


### Bug Fixes

* update version references to dcc-mcp-core 0.18.9 ([170bf4d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/170bf4d698864183ede6f95e58e05c61e386f439))

## [0.4.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.3.3...v0.4.0) (2026-06-07)


### Features

* add houdini-export-preset skill with 4 typed tools ([1ff5c0f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/1ff5c0fe805079592feb0a18b83208215ef4bbf4))
* add houdini-light-rig skill (3-point lighting, HDRI, area softbox) ([53b5104](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/53b5104c36f0d4bcf4543bea9644c8862bbc5dfd))


### Bug Fixes

* auto-format with ruff format in houdini-light-rig scripts ([74c1cbc](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/74c1cbc3ade72106c3b2b676e5d5f57190d1486f))
* resolve Ruff lint errors and SKILL.md compatibility in houdini-light-rig ([6570d70](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/6570d70275bb9295aeefa25ec34fec609a13d52a))
* ruff format and dcc-mcp-core compatibility version in export-preset SKILL.md ([a13b92c](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/a13b92c61be2e822467f1ba0b81b4727b2abd4c1))

## [0.3.3](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.3.2...v0.3.3) (2026-06-07)


### Documentation

* fix houdini-scene-edit load mode in AGENTS.md/README.md ([9f237d7](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/9f237d72248ff06b07d85236ce42e8fdbdd323e5))
* update AGENTS.md/README.md/llms.txt with all 20 skills, add CLAUDE.md and GEMINI.md ([b11ba26](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b11ba2631050d550339306009e903832ebe4d6c5))
* update AGENTS.md/README.md/llms.txt with all 20 skills, add CLAUDE.md/GEMINI.md ([#37](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/37)) ([b11ba26](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b11ba2631050d550339306009e903832ebe4d6c5))

## [0.3.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.3.1...v0.3.2) (2026-06-07)


### Bug Fixes

* **ci:** remove github.token fallback from release-please token ([96b82a1](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/96b82a13fd4e812cd98ccefc36da85b10871ad63))

## [0.3.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.3.0...v0.3.1) (2026-06-07)


### Bug Fixes

* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([962b44f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/962b44fbf6d40b6620c76e980f9c6547878cd1d0))
* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([3ff2b6f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/3ff2b6fd541cdfd6dfbb51e592a43b91bb7a2d5f))
* update dcc-mcp-core repo reference from loonghao to dcc-mcp org ([fdc21ee](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/fdc21eea5f11f90ea97fdbc8badb82777a5a095b))
* update README and skill compatibility to core &gt;=0.18.7, add version consistency test ([b4604de](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b4604de68ce034efa644a9307b4515d9cc8191cb))
* update README and skill compatibility to core &gt;=0.18.7, add version consistency test ([1be87fa](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/1be87faa0aea9fc30ff302ed89772f3ef9bc10c4))

## [0.3.0](https://github.com/loonghao/dcc-mcp-houdini/compare/v0.2.0...v0.3.0) (2026-05-30)


### Features

* add Houdini animation, channel, and timeline skills ([6a9afb5](https://github.com/loonghao/dcc-mcp-houdini/commit/6a9afb5c19f91fc12440810d63385a248a2cdff1))
* add Houdini interchange skill for USD/Alembic/FBX/OBJ/native caches ([1e448b7](https://github.com/loonghao/dcc-mcp-houdini/commit/1e448b7a9c734f1f86cc3e06cacd750919addc3f))
* add Houdini lookdev and shader-network skill ([a5a5ec4](https://github.com/loonghao/dcc-mcp-houdini/commit/a5a5ec4421cf1e1695bd6355cd8a5771f5052831))
* add Houdini render, camera, light, and viewport capture skills ([a9b61be](https://github.com/loonghao/dcc-mcp-houdini/commit/a9b61be9f1160e6549e5e1d347d50b9be46c10a3))
* add Houdini SOP geometry inspection and mesh operation skills ([154d917](https://github.com/loonghao/dcc-mcp-houdini/commit/154d917d4c32a94a0105b16f2d338a88864aa5ae))
* add houdini-dev skill (dev diagnostics + UI interaction) ([5ecb178](https://github.com/loonghao/dcc-mcp-houdini/commit/5ecb1782daee24da980da002b5f57b13f556ba8c))
* add houdini-hda-automation skill (HDA library/validation + PDG/ROP) ([d13aa51](https://github.com/loonghao/dcc-mcp-houdini/commit/d13aa51fdd3cd90e29fe39cac298557be53b4b03))
* add houdini-pipeline skill (project + shot/package automation) ([8bcaecc](https://github.com/loonghao/dcc-mcp-houdini/commit/8bcaeccd7c3d76f45a8f89c87dad983e8838a03e))
* add latest dcc-mcp-core integrations and agent install skill ([b25f28b](https://github.com/loonghao/dcc-mcp-houdini/commit/b25f28b1ae9219417fab2aed3a4337c47ee30e6a))
* **lint:** validate bundled skills with the dcc-mcp-cli runtime validator ([8aa9711](https://github.com/loonghao/dcc-mcp-houdini/commit/8aa9711a377ce2cca2088c090d7393617925be5c))
* **lint:** validate bundled skills with the dcc-mcp-cli runtime validator ([ea38f4b](https://github.com/loonghao/dcc-mcp-houdini/commit/ea38f4ba7b1f15ba2c8f7f5daf2f165af165a1b9))
* **skills:** add Houdini parameters and node-graph skills ([#12](https://github.com/loonghao/dcc-mcp-houdini/issues/12)) ([8ef2695](https://github.com/loonghao/dcc-mcp-houdini/commit/8ef2695a5b1d03f7e415743ad4bd673654611988))
* **skills:** add Houdini scene-edit and object-ops skills ([#11](https://github.com/loonghao/dcc-mcp-houdini/issues/11)) ([042d261](https://github.com/loonghao/dcc-mcp-houdini/commit/042d2619fa536120c7658d71c8fcf3cb3135b564))


### Bug Fixes

* remove unused imports in _qt_inspector module and tests ([5b2368d](https://github.com/loonghao/dcc-mcp-houdini/commit/5b2368d493f526cb84bd13586edaeea124744129))
* remove unused imports in _qt_inspector module and tests ([c70b04a](https://github.com/loonghao/dcc-mcp-houdini/commit/c70b04a3375976740e92310b0ca5a91bda8d0708))
* remove unused imports in _qt_inspector module and tests ([6abfe81](https://github.com/loonghao/dcc-mcp-houdini/commit/6abfe81953dffb8ef00ea790224e3ab0be7480ec))
* remove unused imports in _qt_inspector module and tests ([8053afd](https://github.com/loonghao/dcc-mcp-houdini/commit/8053afd52fcf99f3dd289f6b8688a9b4761a20d6))

## [0.2.0](https://github.com/loonghao/dcc-mcp-houdini/compare/v0.1.0...v0.2.0) (2026-05-25)


### Features

* add PyPI backfill and Houdini material skills ([9842c8b](https://github.com/loonghao/dcc-mcp-houdini/commit/9842c8b16d4bedd6c19ffd909fc8ebda17cddeb2))


### Bug Fixes

* keep release runtime version managed ([6ca6a39](https://github.com/loonghao/dcc-mcp-houdini/commit/6ca6a39291b3b668ae0674df370083f6fe8b518e))


### Documentation

* clarify release artifact install ([41cc439](https://github.com/loonghao/dcc-mcp-houdini/commit/41cc439bc2b959d77da2d166bd3319fe836b34e4))

## 0.1.0

- Initial Houdini MCP adapter foundation.
- Embedded MCP Streamable HTTP server with progressive bundled skills.
- Houdini scripting, scene inspection, node authoring, HDA, and automation skills.
- Wheel, sdist, and Houdini quickinstall package assembly.
- CI, release, and optional licensed Houdini Docker E2E workflows.
