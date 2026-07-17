# Changelog

## Unreleased

### Features

* share owned isolated ROP jobs across renders, simulation caches, and ROP chains
* derive bounded output progress and ETA during job polling
* make `build_node_chain` an atomic prevalidated transaction with dry-run, one-step undo, explicit rollback, and scene readback
* report created, connected, and parameter summaries for structured node recipes
* replace HIP targets atomically after a successful temporary save

### Bug Fixes

* reject dirty GUI background launches and persist explicit headless background launches before rendering
* avoid false failures for successful ROP chains without discoverable output paths
* preserve `ignore_inputs` for isolated Solaris ROP chains

## [0.20.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.20.0...v0.20.1) (2026-07-17)


### Bug Fixes

* **installer:** support isolated Houdini package directory ([#149](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/149)) ([626997c](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/626997c193d80fa4ebd6a81f53feb5f301de357a))

## [0.20.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.19.0...v0.20.0) (2026-07-17)


### Features

* validate known Karma stage diagnostics ([#147](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/147)) ([da4c17a](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/da4c17a8b55c43ba07765cd595d519be4c16afc6))

## [0.19.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.18.3...v0.19.0) (2026-07-17)


### Features

* add reusable HDA authoring contracts ([#145](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/145)) ([2a2b60c](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/2a2b60c003c4471cc3aff6fe2662308cee13d2a2))

## [0.18.3](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.18.2...v0.18.3) (2026-07-17)


### Bug Fixes

* **render:** separate ROP errors and warnings ([eb83a36](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/eb83a366a0239713c681f1945c9bf94c1369bc33))

## [0.18.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.18.1...v0.18.2) (2026-07-17)


### Bug Fixes

* preserve promoted HDA interfaces ([#140](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/140)) ([a89a3d4](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/a89a3d49c7586424076a0631a00fcc4f8b848196))
* wait through Windows termination races ([#141](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/141)) ([fb94523](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/fb94523764f3e897e0210aca78e02d4f4bd35de1))

## [0.18.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.18.0...v0.18.1) (2026-07-17)


### Bug Fixes

* terminate Windows render jobs without taskkill ([#138](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/138)) ([fa8474e](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/fa8474ea9e92b3d6578e230567b26786d811402e))

## [0.18.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.5...v0.18.0) (2026-07-17)


### Features

* complete reusable HDA lifecycle ([e17f5b9](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e17f5b9582e38d5a1774e410b4ff7a6d5e65ffad))

## [0.17.5](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.4...v0.17.5) (2026-07-17)


### Bug Fixes

* **packaging:** preserve Houdini autostart override ([#134](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/134)) ([deefcb1](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/deefcb11558dfe61f0b56cc55bc08b3dc790da78))

## [0.17.4](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.3...v0.17.4) (2026-07-16)


### Bug Fixes

* honor Houdini flipbook increments and camera selection ([#130](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/130)) ([ce40084](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ce4008423aa653d57f9c374efd695472351609d0))

## [0.17.3](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.2...v0.17.3) (2026-07-16)


### Bug Fixes

* use OS-assigned MCP instance ports ([#128](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/128)) ([9230341](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/923034138df39d692fd694bb1b4b8ea9b9b2697e))

## [0.17.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.1...v0.17.2) (2026-07-16)


### Bug Fixes

* budget Houdini UI host dispatch ([#126](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/126)) ([1128ef4](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/1128ef4986d552309b61ab294d31769047b8460e))

## [0.17.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.17.0...v0.17.1) (2026-07-16)


### Bug Fixes

* report live render outputs and diagnostics ([#124](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/124)) ([c9749aa](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/c9749aae537f081a8bb2a595b700760d5f5b48b2))

## [0.17.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.16.3...v0.17.0) (2026-07-16)


### Features

* **skills:** add read-only Solaris USD inspection ([#122](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/122)) ([eefab7c](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/eefab7ccc27b1ced452574d9be8edfe2157f056e))

## [0.16.3](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.16.2...v0.16.3) (2026-07-16)


### Bug Fixes

* refresh quickinstall vendor import caches ([b22ce5d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b22ce5d7acecf0f2ddba329ffd8374140f66e947))
* refresh quickinstall vendor import caches ([2cc8b3b](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/2cc8b3b09a64f3700a5e512fa736c953b14d74a1))
* report partial render outputs accurately ([#121](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/121)) ([10b7b86](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/10b7b866c3c9cee87765df5a632cd1a0beada9df))

## [0.16.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.16.1...v0.16.2) (2026-07-16)


### Bug Fixes

* write Houdini package JSON without UTF-8 BOM ([#117](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/117)) ([8a622a7](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/8a622a7903850ace45c70cc7daac760cb37545c0))

## [0.16.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.16.0...v0.16.1) (2026-07-16)


### Bug Fixes

* autostart when opening Houdini scenes ([#115](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/115)) ([b958a47](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b958a47b9410492dd3b3e9218e12d5228eee5abf))

## [0.16.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.15.0...v0.16.0) (2026-07-16)


### Features

* report atomic node recipe outcomes ([#113](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/113)) ([afd45af](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/afd45af25a2f318dd8b35621f78da1475d0bf986))

## [0.15.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.14.0...v0.15.0) (2026-07-16)


### Features

* make node-chain builds atomic ([#111](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/111)) ([f94d9d3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/f94d9d3953f6da2b48c9fb5745202964fe564c62))

## [0.14.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.13.0...v0.14.0) (2026-07-16)


### Features

* isolate long-running ROP jobs ([#109](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/109)) ([08f7ab3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/08f7ab30eb8bb593deab09586e4d36ae62a04dfb))
## [0.13.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.12.0...v0.13.0) (2026-07-16)


### Features

* add cancellable background render jobs ([#107](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/107)) ([0bd0ca3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/0bd0ca39ecfa0eb5e0771a05f2cd3e7ae21ec8fb))

## [0.12.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.5...v0.12.0) (2026-07-16)


### Features

* add non-blocking ROP render jobs ([13d6fcf](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/13d6fcff94714af7bf8ad867e37db05662257824))


### Bug Fixes

* keep interactive ROP renders off the UI thread ([#106](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/106)) ([4a6d244](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/4a6d244bba821d32018fb219d0d858f7db2d1915))
* recover mixed-version render jobs ([0bc0213](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/0bc0213345bd6455f08c35ee93a435bd955088bc))
* reject stale background render outputs ([c951caf](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/c951caf227c1624f61f4a073f23ee532d7d3b638))
* suppress adapter startup in render workers ([94631f8](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/94631f8c1ff42f459dc690cd7e206472a290c09d))

## [0.11.5](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.4...v0.11.5) (2026-07-14)


### Bug Fixes

* enforce Husk render contracts ([b14df92](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b14df925eee180cd1cbf2eec16dfe899387dd44a))
* silence Houdini HTTP logs ([fe95fdb](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/fe95fdbb72a2e62afbb2098954daf2940ce3e23e))

## [0.11.4](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.3...v0.11.4) (2026-07-12)


### Documentation

* add six dcc particle showcase ([#97](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/97)) ([70e89ac](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/70e89acb134c2a3388429f18bfac87e8e809217e))

## [0.11.3](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.2...v0.11.3) (2026-07-11)


### Bug Fixes

* support standalone main-thread execution ([481ecda](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/481ecda7dbffce07aa0bd9b72a218c35de90b83d))

## [0.11.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.1...v0.11.2) (2026-07-09)


### Bug Fixes

* keep Houdini registry registration enabled ([d672351](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d672351e9f1b501e3fd9f05ead0074022c7d1e29))

## [0.11.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.11.0...v0.11.1) (2026-07-08)


### Bug Fixes

* allow validated core pin for Houdini quickinstall ([17398a5](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/17398a5d805de260f00f11b35f7bf819bda1106e))

## [0.11.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.10.1...v0.11.0) (2026-07-08)


### Features

* add Houdini quickinstall shelf controls ([718a687](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/718a6879c9639c8633f6141a51db1fffb35d84b3))

## [0.10.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.10.0...v0.10.1) (2026-06-30)


### Bug Fixes

* recover main from v0.10.0 ([bce408b](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/bce408b7ed9af338de6238f992c32bc0f4d112df))


### Documentation

* **AGENTS.md:** rename Tools to Key tools in Bundled Skills tables ([#81](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/81)) ([ef15bea](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ef15bea0227d99abb817ff04bee9affbb2d199b9))
* correct gateway port and bundled skill/tool counts ([#86](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/86)) ([d9756b5](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d9756b5d6b74a316869a9847d4fad612eea171f2))
* update example wheel URL from v0.1.0 to v0.9.1 ([78b022f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/78b022f4ac7e3362d70be3245b44c0c248716362))

## [0.10.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.9.0...v0.10.0) (2026-06-24)


### Features

* add dcc-mcp-houdini project with dev workflow ([fe752d3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/fe752d3318683e54100a20c10360522d9d591a5e))
* add Houdini animation, channel, and timeline skills ([b69fdab](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b69fdabd336670dc75e4f0ca9d9107288fa49315))
* add Houdini interchange skill for USD/Alembic/FBX/OBJ/native caches ([f265310](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/f2653101e687757a65860bce6ddcaedce6a47fec))
* add Houdini lookdev and shader-network skill ([8f28dad](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/8f28dad71d8f217bbf8e58e08357b1da5f552cc9))
* add Houdini render, camera, light, and viewport capture skills ([36027ff](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/36027ff46d5ab9cc1a38c0bb2ebac65b1aa13562))
* add Houdini SOP geometry inspection and mesh operation skills ([620a116](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/620a116850c9a54925f9410c9fd72eb7eb90586b))
* add houdini-chops, houdini-constraints, and houdini-kinefx skills (PIP-1297) ([8b20120](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/8b201202b639e0970cc1b78e8e2c19437ad592c7))
* add houdini-dev skill (dev diagnostics + UI interaction) ([e2e3bd6](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e2e3bd6e42a7ed9355ba3eb8c7299e8815fa1f53))
* add houdini-export-preset skill with 4 typed tools ([f4e50e3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/f4e50e313ad386d6b18f9de4fada8ee4a2294655))
* add houdini-hda-automation skill (HDA library/validation + PDG/ROP) ([54b783e](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/54b783eaac4e45a908997248454088052e70a508))
* add houdini-import-to-scene skill for cross-DCC asset import ([#71](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/71)) ([d8a3d60](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d8a3d60d7a5a5546924b7b917262bb0dfdbc4449))
* add houdini-karma and houdini-husk skill packages (PIP-1298) ([e0ded64](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e0ded64837730294c6de3c9f5ecb05c98e233294))
* add houdini-light-rig skill (3-point lighting, HDRI, area softbox) ([a44a621](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/a44a621df5f14073bcf2a2553a2c71bc4f2792b1))
* add houdini-material-library skill with 12 tools ([ed909eb](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ed909eb97fd799f9e71b7604bfeac23e2c3f37eb))
* add houdini-pipeline skill (project + shot/package automation) ([d8aefcb](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d8aefcb359a37efe6c7dda38123a6aa0a53272a4))
* add houdini-texture-bake skill with 5 typed bake tools ([b1b9988](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b1b9988e3b93741718288e19d72993a056e8819a))
* add latest dcc-mcp-core integrations and agent install skill ([000e800](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/000e800e9c34cff2f617ce197973e3d976f227e0))
* add PyPI backfill and Houdini material skills ([7ed343f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/7ed343f2b9ca87ef081ce008db463e803835f03d))
* complete Houdini adapter release foundation ([5ecd37b](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/5ecd37b8adde742bb11a5a1836833e6f5670db6f))
* **lint:** validate bundled skills with the dcc-mcp-cli runtime validator ([29ecb4a](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/29ecb4a67c8ca164846dd5870d6e25e7d254d1cc))
* **lint:** validate bundled skills with the dcc-mcp-cli runtime validator ([ed3a814](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ed3a8144a06bc3e766443a2619ebc4fbe7818e18))
* **skills:** add Houdini parameters and node-graph skills ([#12](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/12)) ([237ba7d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/237ba7df230215d897b82399eac9b65e0acd6c73))
* **skills:** add Houdini scene-edit and object-ops skills ([#11](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/11)) ([d08022d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d08022d814eb2cc7a5b56b752504de368a867212))


### Bug Fixes

* auto-format with ruff format in houdini-light-rig scripts ([b066326](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b0663261fe93dbddbcfd798c26df7e29613c3814))
* **ci:** apply ruff formatting to install_dcc_mcp_cli.py ([ee032a7](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ee032a725222f1780a73eb3837d35a342240f0f2))
* **ci:** fallback through recent releases when latest lacks CLI binary ([bba8420](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/bba8420344da534bf91498a4308c5c7391ec82c6))
* **ci:** fix import sorting in test_agent_instruction_files.py ([da12590](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/da125908d18ee9887ac5bf3863a61a2a51400deb))
* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([3c19bc2](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/3c19bc2498de51981429c008d6eafb6293d97ebf))
* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([aa24e8c](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/aa24e8cd8b1d95505983d7b89bbba5c19660837d))
* **ci:** remove github.token fallback from release-please token ([77d2789](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/77d2789898d6ee299d2831e475a8f91503b9792a))
* correct 3 skill tool tables in docs (NACK follow-up) ([a55dea3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/a55dea34f7f9908b184654b64c4e9979a56de9c1))
* keep release runtime version managed ([00ba740](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/00ba74022201da2ab74730b59bef20a18744a2a9))
* lint errors in houdini-texture-bake skill scripts ([7420186](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/74201865cc1a40d3bb219d0c1c59b4f8387055c1))
* remove unused imports in _qt_inspector module and tests ([059dd61](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/059dd61a33088e854865c2f3478e1d29f5b7b373))
* remove unused imports in _qt_inspector module and tests ([83c4531](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/83c45315282cbccbd5d9be8cd1173fa4a84c58c9))
* remove unused imports in _qt_inspector module and tests ([6855c43](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/6855c430c9674b19a136cb07016993c49e6601fc))
* remove unused imports in _qt_inspector module and tests ([ecefebd](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/ecefebd930641bb916a6a0790945f0dec44c50fc))
* resolve Ruff lint errors and SKILL.md compatibility in houdini-light-rig ([adfb359](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/adfb3590d7589045ebfda281f4ba8ab6cb6cb69d))
* review feedback — rebase, remove redundant baker_available, add tests ([1d4a60f](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/1d4a60fef771b5095ed4b22aee0b4c3df1f4d6a3))
* ruff format and dcc-mcp-core compatibility version for material-library skill ([4b6de74](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/4b6de74915eb6e10d7322a8e22d0ff3a6ead2401))
* ruff format and dcc-mcp-core compatibility version in export-preset SKILL.md ([da52e70](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/da52e70478b516f7aa2ce3ad35d4c4db30693402))
* sort imports in setup_dcc_mcp_houdini.py (I001 ruff) ([b61a760](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b61a76041904a12819726513a2980223a2f796ed))
* sync STAGE_SKILLS with 4 newly added skills ([438aec8](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/438aec8f60c1425f1e0053ae2d2150535e94e05b))
* update dcc-mcp-core repo reference from loonghao to dcc-mcp org ([b36d1fa](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/b36d1fa0cb0af5a3e9a9ba8c135d9ddc66ddd635))
* update README and skill compatibility to core &gt;=0.18.7, add version consistency test ([4927e22](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/4927e225957d53cdc1e88a4e080ff213cf938bf4))
* update README and skill compatibility to core &gt;=0.18.7, add version consistency test ([c172482](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/c17248287b1c83a65247567694e38169883d2bd2))
* update version references to dcc-mcp-core 0.18.9 ([35db543](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/35db543c9b8261353b2fe641c1cc725fa184c94a))


### Documentation

* clarify release artifact install ([41cc439](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/41cc439bc2b959d77da2d166bd3319fe836b34e4))
* fix houdini-scene-edit load mode in AGENTS.md/README.md ([0814ef7](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/0814ef7221a54e5f4ca222ea5894cad391eebca3))
* sync bundled skills table with v0.8.0 ([6814fe3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/6814fe32d36b6261ac61bd0e7a927b8a741b9249))
* sync bundled skills table with v0.8.0 ([38e7655](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/38e7655503cf51726580f41a8a199cc4bb091e2c))
* sync bundled skills table with v0.8.0 ([#69](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/69)) ([6814fe3](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/6814fe32d36b6261ac61bd0e7a927b8a741b9249))
* sync skill counts, add missing houdini-import-to-scene, fix stage categorization ([13ac952](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/13ac9528b0ba8a1741a6d965b108fbaca13b89eb))
* update AGENTS.md/README.md/llms.txt with all 20 skills, add CLAUDE.md and GEMINI.md ([e436aef](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e436aefb4fe9c5bbef1e2258f0d814284d1c3a19))
* update AGENTS.md/README.md/llms.txt with all 20 skills, add CLAUDE.md and GEMINI.md ([e8e4613](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e8e4613c2e3c86f0b63f246c435923cc257dead9))
* update AGENTS.md/README.md/llms.txt with all 20 skills, add CLAUDE.md/GEMINI.md ([#37](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/37)) ([e436aef](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/e436aefb4fe9c5bbef1e2258f0d814284d1c3a19))
* update example wheel URL from v0.1.0 to v0.9.1 ([8b82b51](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/8b82b51b05a30ebc2c4300bbee91adbad9cea613))
* update example wheel URL from v0.1.0 to v0.9.1 ([8b82b51](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/8b82b51b05a30ebc2c4300bbee91adbad9cea613))
* update example wheel URL from v0.1.0 to v0.9.1 ([7bde6af](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/7bde6afee4701388a3f5543443e3c868a947c782))

## [0.9.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.8.1...v0.9.0) (2026-06-20)


### Features

* add houdini-import-to-scene skill for cross-DCC asset import ([#71](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/71)) ([4b3360d](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/4b3360d9569479047f22cddd1c52ffafffc9e60a))


### Documentation

* sync skill counts, add missing houdini-import-to-scene, fix stage categorization ([948fcaf](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/948fcafbcd8edb9ad7afcc0b59aef38a4c62269c))

## [0.8.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.8.0...v0.8.1) (2026-06-19)


### Bug Fixes

* correct 3 skill tool tables in docs (NACK follow-up) ([25ba260](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/25ba2601796de6fd70ada9dc21bff2ce66d76e4b))


### Documentation

* sync bundled skills table with v0.8.0 ([aa5ef6b](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/aa5ef6befeb72aee49eef465ecd41bfe373affe5))
* sync bundled skills table with v0.8.0 ([5b0824e](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/5b0824e1ec603abb8a076a3f37bc13c1d9e47bd8))
* sync bundled skills table with v0.8.0 ([#69](https://github.com/dcc-mcp/dcc-mcp-houdini/issues/69)) ([aa5ef6b](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/aa5ef6befeb72aee49eef465ecd41bfe373affe5))

## [0.8.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.7.0...v0.8.0) (2026-06-17)


### Features

* add houdini-karma and houdini-husk skill packages ([2d52dba](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/2d52dba7466d0d154b1bafc736d1d96012e9495b))

## [0.7.0](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.6.2...v0.7.0) (2026-06-14)


### Features

* add houdini-chops, houdini-constraints, and houdini-kinefx skills ([3e35afe](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/3e35afeed9f8299505cef802cca7b7734fa4fa1f))

## [0.6.2](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.6.1...v0.6.2) (2026-06-08)


### Bug Fixes

* sync STAGE_SKILLS with 4 newly added skills ([2cae258](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/2cae258875f881f443da292120d6606639421b7e))

## [0.6.1](https://github.com/dcc-mcp/dcc-mcp-houdini/compare/v0.6.0...v0.6.1) (2026-06-08)


### Bug Fixes

* sort imports in setup_dcc_mcp_houdini.py (I001 ruff) ([d92372a](https://github.com/dcc-mcp/dcc-mcp-houdini/commit/d92372a2bcfe627b08b6ec600df9fbb0beb6bf7f))

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
