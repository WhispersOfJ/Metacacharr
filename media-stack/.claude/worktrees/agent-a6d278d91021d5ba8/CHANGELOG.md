# Changelog

## [11.16.0](https://github.com/WhispersOfJ/media-stack/compare/v11.15.0...v11.16.0) (2026-08-20)


### Features

* add Browser Games category to catalog (3 verified entries) ([6368a00](https://github.com/WhispersOfJ/media-stack/commit/6368a00627a43902d99451b7aa39c44f43560817))
* add collapsible environment/volume details to catalog cards ([d713736](https://github.com/WhispersOfJ/media-stack/commit/d7137360b6843257305ede15f83fce1c35a3125c))
* add diagonal-hatch texture layer to page background ([fdc0954](https://github.com/WhispersOfJ/media-stack/commit/fdc09547a7e934c4f8ac4ab1f00a1da4f96be1de))
* add Media category to catalog (8 verified entries) ([4b2ae62](https://github.com/WhispersOfJ/media-stack/commit/4b2ae62e60ff20072e786c0b18ae24c8b94928fe))
* add per-group CPU sparkline history to Fleet rail ([7e3c7cd](https://github.com/WhispersOfJ/media-stack/commit/7e3c7cdb144316970b399f063059b5716c6c333d))
* add RetroArch Emulation category to catalog (12 verified entries) ([f8a9a87](https://github.com/WhispersOfJ/media-stack/commit/f8a9a871304dadeeeee1a3008c8b40bf615998f2))
* add shared logger + 108 tests for control-panel/core/ ([f1cb35e](https://github.com/WhispersOfJ/media-stack/commit/f1cb35e6e8cf9003ac14e72d7bf4e1c935e141d5))
* default control-panel theme to amber Pip-Boy palette ([9965440](https://github.com/WhispersOfJ/media-stack/commit/996544098bd1717ef357de184a500429bf198bfb))
* give each rail a distinct accent hue ([d4ee752](https://github.com/WhispersOfJ/media-stack/commit/d4ee752c7e10f1d7f67c43c186dc03d070a89e17))
* include environment and volumes in catalog list response ([560bb41](https://github.com/WhispersOfJ/media-stack/commit/560bb41b34493d66519300325010fbad659ec26e))
* Plan 3 severe consolidation — remove 7 services, merge anime into base Radarr/Sonarr ([517978a](https://github.com/WhispersOfJ/media-stack/commit/517978a56ce644d43e62845f260acc3f379732ae))
* promote poster sync to top rail, remove software catalog rail ([dc9f4c1](https://github.com/WhispersOfJ/media-stack/commit/dc9f4c1c4f4813e2e23de77d1ab4d61de3824c53))
* replace dark/light theme with amber/green Pip-Boy CRT palette ([3129195](https://github.com/WhispersOfJ/media-stack/commit/31291956d35cf2496cf1616cbddcf1689515e98d))
* wire amber/green theme switch, delete software catalog module ([0c701f5](https://github.com/WhispersOfJ/media-stack/commit/0c701f5e75825b5a64776b3a3d845a6d98bc4bca))
* wire InfiniDysk Prowlarr pull-sync now that v1.1.0+ is stable ([b746438](https://github.com/WhispersOfJ/media-stack/commit/b746438eff7be943ad19df07ae92d953e77b8f3c))


### Bug Fixes

* address final-review findings (theme PATCH schema, dead CSS, fragile selector) ([475c078](https://github.com/WhispersOfJ/media-stack/commit/475c07823a7183f3004d4fde65b5770c8b402060))
* catalog details panel display:flex overrode [hidden], never collapsed ([ff650a6](https://github.com/WhispersOfJ/media-stack/commit/ff650a6b7087aa4f57c31181c9f94b4700690921))
* clear ruff lint errors blocking Validate Compose CI ([dc27428](https://github.com/WhispersOfJ/media-stack/commit/dc274287dabea6411d1785da0666388e69f8b33f))
* declare FUSE-mount dependency chain, add rclone healthcheck ([a02163a](https://github.com/WhispersOfJ/media-stack/commit/a02163acab7565d0073ed779660f2fb66f26679f))
* diverge --rail-plex-health from --bad to avoid error-color collision ([d4e4ab0](https://github.com/WhispersOfJ/media-stack/commit/d4e4ab09079b81576e096fc4462441a55c9b1296))
* guard unhandled Cleanuparr seeker fetch, add 23 script tests ([10ce1d1](https://github.com/WhispersOfJ/media-stack/commit/10ce1d1722a1462b621179e8dea6e70670651483))
* isolate router-import failures instead of crashing all of boot ([10f545f](https://github.com/WhispersOfJ/media-stack/commit/10f545f758239336e0a81ed5851e982fdc1f4f11))
* log silent excepts, justify automation routes, add 35 router tests ([0df6ac1](https://github.com/WhispersOfJ/media-stack/commit/0df6ac16c8470816c2d575900283a85606d417ff))
* remove dangling env vars for services deleted in consolidation ([922831c](https://github.com/WhispersOfJ/media-stack/commit/922831cecb407ee6afb5b2d6efd728080021b4f9))
* remove dead sparkline CSS rules, diverge rail-fleet/rail-catalog from status colors ([113d38c](https://github.com/WhispersOfJ/media-stack/commit/113d38cd0d6d8fdd40c14e6dd59e580197f4c09f))
* remove stale extras profile refs, fix dangling app.py COPY ([7eb9af6](https://github.com/WhispersOfJ/media-stack/commit/7eb9af644b414f6715f92753d630a6d7211c0518))
* restore RAM sparkline green color and fill styling ([9c070b3](https://github.com/WhispersOfJ/media-stack/commit/9c070b3cabb92037574bd59d99bccdd5db8197a8))
* update control-panel unit tests for amber/green theme default ([56840a0](https://github.com/WhispersOfJ/media-stack/commit/56840a0bd104696148d0f669487c118d29ec7854))


### Performance Improvements

* bump nzbdav queue worker count from 3 to 6 ([718bcbe](https://github.com/WhispersOfJ/media-stack/commit/718bcbef5aa3e983c568cf0cce98e1420c421ed1))

## [11.15.0](https://github.com/WhispersOfJ/media-stack/compare/v11.14.0...v11.15.0) (2026-08-14)


### Features

* reach every Arr instance from the CLI, and generate tab completions ([b13311b](https://github.com/WhispersOfJ/media-stack/commit/b13311b5be61daa19ee559f32e87c7f1f86ce7eb))
* surface radarr-anime and sonarr-anime across the Control Panel ([673bd16](https://github.com/WhispersOfJ/media-stack/commit/673bd1689ac955536957a7b6f9e54e3c585e0f2f))


### Bug Fixes

* send the service API key from the Plex health watchdog ([76a2f66](https://github.com/WhispersOfJ/media-stack/commit/76a2f662daae00dcdae9ec195256363a3975067f))

## [11.14.0](https://github.com/WhispersOfJ/media-stack/compare/v11.13.0...v11.14.0) (2026-08-14)


### Features

* --anime/--sonarr-anime flags across fish CLI, new mdblist tracking commands ([fee0098](https://github.com/WhispersOfJ/media-stack/commit/fee00989ad90045ddcebb6e60fc79973b9b48bf2))
* add curated software catalog (Phase 02 of the v3 design treatment) ([22d00cb](https://github.com/WhispersOfJ/media-stack/commit/22d00cba670f440b5068c7e9c79101588817bafc))
* add disk health, live host resources, and backup UI (Phase 03) ([321a8be](https://github.com/WhispersOfJ/media-stack/commit/321a8be80bbdf695aae8153f8b9774a2d36a3f9b))
* add GAPS-2 (collection/franchise gap detection for movies and TV) ([3e7eee1](https://github.com/WhispersOfJ/media-stack/commit/3e7eee15bdf3bd71a230085bae07df3dc6881a84))
* add host-privileged-action helper (reboot, pacman sync/upgrade) ([c627a61](https://github.com/WhispersOfJ/media-stack/commit/c627a61d90e67c324abc885bfba8069ffda4d1be))
* add Letterboxd cache, tracked-list, and sync-log models ([a20bfa6](https://github.com/WhispersOfJ/media-stack/commit/a20bfa6e7ecd283ac69ea5d7a2204ea7b9863c2e))
* add news.newshosting.com as tertiary nzbdav usenet provider ([ed790b0](https://github.com/WhispersOfJ/media-stack/commit/ed790b093bfe5731252faf2ef974116086bed72d))
* add ntfy (shared push-notification sink for Radarr/Sonarr/Prowlarr) ([2b70fae](https://github.com/WhispersOfJ/media-stack/commit/2b70faecfcd8c4165bcd84c56d52815d45a0827a))
* add Organizr (single landing dashboard for the whole stack) ([7981026](https://github.com/WhispersOfJ/media-stack/commit/79810269648f512422c5cfccb89dae44109d72fe))
* add persisted settings and rack-console redesign to control-panel ([8822d7b](https://github.com/WhispersOfJ/media-stack/commit/8822d7b78165604b16dbcfa54f6d4979437d5a4a))
* add plex-marked-deleted-db-contention diagnosis skill ([72dd457](https://github.com/WhispersOfJ/media-stack/commit/72dd4574a601e3388464f0711eb092ea0460f984))
* add PlexAniSync (Phase 7) - anime watch state from Plex to AniList ([c5bb824](https://github.com/WhispersOfJ/media-stack/commit/c5bb8244c258dae030c9ebc635961ca82461302a))
* add Poster Studio gallery, before/after preview, quality scan (Phase 04) ([95c5cec](https://github.com/WhispersOfJ/media-stack/commit/95c5cecc7014fe5d53a7c3f41a6a359eddf1d58a))
* add Scrutiny (SMART trending + failure prediction for the host disk) ([01f2967](https://github.com/WhispersOfJ/media-stack/commit/01f2967fd6f551047f6f3a5947414fd7a05c0760))
* add Speedtest Tracker (hourly ISP link monitoring + history) ([43ed2fb](https://github.com/WhispersOfJ/media-stack/commit/43ed2fb028cddde0d5029e8be88dddf9f1b971ad))
* add stack-plex-butler-all fish function ([691ac83](https://github.com/WhispersOfJ/media-stack/commit/691ac8344203efcc24386acdb429cc0a8218f443))
* add WatchState (Phase 6) - Plex watch-state sync via import + webhook ([ff651a9](https://github.com/WhispersOfJ/media-stack/commit/ff651a953a650eaa92622eb879e94e55fc4c9850))
* anime Radarr/Sonarr support in Letterboxd import routes ([bb9a5c9](https://github.com/WhispersOfJ/media-stack/commit/bb9a5c961979b10206954db7cc4c510a50ad8c0d))
* attach scraped Letterboxd tags as Radarr tags on add ([62ec168](https://github.com/WhispersOfJ/media-stack/commit/62ec168553d7eafbdcf1b24302b8a68f3ade4dfc))
* cache Letterboxd slug-&gt;TMDb id lookups to skip re-fetching known slugs ([6ad02e2](https://github.com/WhispersOfJ/media-stack/commit/6ad02e2f5ae00f6e4a13a3551bf4b503fc64aa9b))
* **control-panel:** Phase 1 of evolved backend - scaffolding + auth ([ef98a82](https://github.com/WhispersOfJ/media-stack/commit/ef98a82714c78fee3be42d7aeab522dabbd6a326))
* **control-panel:** Phase 2 of evolved backend - fleet + settings ([50a3cff](https://github.com/WhispersOfJ/media-stack/commit/50a3cffa3b9213d0e3ceaf56c9c7cb076fb5dbb0))
* **control-panel:** Phase 3 of evolved backend - Radarr/Sonarr/Prowlarr/Bazarr ([90bd869](https://github.com/WhispersOfJ/media-stack/commit/90bd86975e0519363ecccf6291438a94d6f87c7d))
* **control-panel:** Phase 4 part 1 - Plex router ([c3a5191](https://github.com/WhispersOfJ/media-stack/commit/c3a5191fb1aa7d453ce00ffdf1dc8d64a7694143))
* **control-panel:** Phase 4 part 13 - new-apps health/backup sweep router ([307c152](https://github.com/WhispersOfJ/media-stack/commit/307c152ad918a14741ebd0041c5a8cfc9f8d84ce))
* **control-panel:** Phase 4 part 14 - poster-sync router (final Phase 4 service) ([f277078](https://github.com/WhispersOfJ/media-stack/commit/f2770780396967bd50d4caa92241e0a203c93e62))
* **control-panel:** Phase 4 part 2 - NzbDAV router ([5aeff6f](https://github.com/WhispersOfJ/media-stack/commit/5aeff6f18596761f400aef2893bb2fc2aeb0c51f))
* **control-panel:** Phase 4 part 3 - host diagnostics ([4924fa8](https://github.com/WhispersOfJ/media-stack/commit/4924fa8aeeb8a906788fce21da83c93b31dd4050))
* **control-panel:** Phase 4 part 4 - backups router ([dd2a973](https://github.com/WhispersOfJ/media-stack/commit/dd2a973cbf216edd925abffcc580347ab8a3506d))
* **control-panel:** Phase 4 part 5 - Tautulli router ([894dd23](https://github.com/WhispersOfJ/media-stack/commit/894dd2388cc5d6e1aa2dfc2e5c82fb05b3ba9f2b))
* **control-panel:** Phase 4 part 6 - Wrapperr router ([18223e5](https://github.com/WhispersOfJ/media-stack/commit/18223e5197762136f36ed6b96001f8d90264970b))
* **control-panel:** Phase 4 part 8 - Maintainerr router ([29fe5e6](https://github.com/WhispersOfJ/media-stack/commit/29fe5e6820ff7abaee74a0f9e7a4a1a578a8b84d))
* **control-panel:** Phase 4 part 9 - Checkrr router ([bcf89ff](https://github.com/WhispersOfJ/media-stack/commit/bcf89ff0f5a837c8fccd41e4edf82939ea262e7b))
* **control-panel:** Phase 4 parts 10-12 - Prefetcharr/Lingarr/Kometa routers ([b7403c2](https://github.com/WhispersOfJ/media-stack/commit/b7403c23dcacc24ba062f714689f555be1d3057a))
* **control-panel:** Phase 5 cutover - flip live backend from app.py to main.py ([8ad0e89](https://github.com/WhispersOfJ/media-stack/commit/8ad0e89d9cdeefb6b462a6adb335d19535a77a38))
* **control-panel:** redesign as a piping-and-instrumentation diagram ([699cac1](https://github.com/WhispersOfJ/media-stack/commit/699cac11e9c3c6e039b3b4ad076641c4d7baf664))
* **control-panel:** register radarr-anime instance (core/arr_client.py, core/docker_client.py) ([c56feed](https://github.com/WhispersOfJ/media-stack/commit/c56feed46ba01f0605d8997282c8cdc403d387ba))
* cross over TMDb-unmatched Letterboxd titles to Sonarr via series lookup ([3f9f22f](https://github.com/WhispersOfJ/media-stack/commit/3f9f22faf9faea479fd2650e1616930ffb877396))
* cut fish functions over to symlinks, drop restic orphans (Phase 8a) ([610926c](https://github.com/WhispersOfJ/media-stack/commit/610926c741a6cce7239b3ffed8692e674cfb983c))
* cut GAPS-2 to Movies/Shows and wire its Radarr/Sonarr ([da052cf](https://github.com/WhispersOfJ/media-stack/commit/da052cfb21cd64fe5a505170738d6c5cd1c70477))
* dashboard panel for tracked Letterboxd lists + sync history ([d09d9be](https://github.com/WhispersOfJ/media-stack/commit/d09d9be364875b448cdd259aeaea9a27c5a5627e))
* detect and auto-clear Radarr/Sonarr import starvation ([860e27e](https://github.com/WhispersOfJ/media-stack/commit/860e27ece96c0228817daf47beded79716d6d129))
* enable InfiniDysk repair, streaming perf, and safety settings ([17db2d3](https://github.com/WhispersOfJ/media-stack/commit/17db2d35314a18c852c559d186dbb36bfd0e0a34))
* fish CLI commands for Letterboxd tracked-list sync + history ([217e833](https://github.com/WhispersOfJ/media-stack/commit/217e833a98617343819e6ee5574570b5874b1760))
* MDBList as its own package, with anime Radarr/Sonarr routing ([c6ab624](https://github.com/WhispersOfJ/media-stack/commit/c6ab624733e53e09672be1217b7642d9ae2eafc1))
* nightly systemd-scheduled sync for tracked Letterboxd lists ([d552ae6](https://github.com/WhispersOfJ/media-stack/commit/d552ae6ff9e734ef37e8d5dd39d8ffd7a2eaa8f7))
* **plex:** mount anime-movies path for the new Anime Movies library ([b4b8b54](https://github.com/WhispersOfJ/media-stack/commit/b4b8b540a96fab26eadad716fda68219dc47c755))
* **radarr-anime:** add dedicated Radarr instance for anime movies ([5be2982](https://github.com/WhispersOfJ/media-stack/commit/5be29829b93b6d8f38731e8c98195dcf7bbda33e))
* **radarr:** add Criterion Collection custom format ([d667f50](https://github.com/WhispersOfJ/media-stack/commit/d667f500d70ee4c999e587b0af8fb630f9086a21))
* raise usenet provider max connections to 50 ([dcef798](https://github.com/WhispersOfJ/media-stack/commit/dcef7983e93c8565830f443b621b2ff79a934a55))
* rating-aware quality-profile mapping for Letterboxd list adds ([bfa89cd](https://github.com/WhispersOfJ/media-stack/commit/bfa89cd12034679104e6cc5f4853ec67e00c2da1))
* re-add news.newshosting.com as tertiary nzbdav usenet provider ([8fe471f](https://github.com/WhispersOfJ/media-stack/commit/8fe471fe526f4ee7a35a102e9b771b8ef1f145de))
* reconcile Radarr/Sonarr file lists against Plex by exact path ([f6ad170](https://github.com/WhispersOfJ/media-stack/commit/f6ad170799fb7695499dd501a1fc5f608bce9642))
* record + surface Letterboxd sync telemetry (GET /api/arr/letterboxd/history) ([d6dec04](https://github.com/WhispersOfJ/media-stack/commit/d6dec04687ec7a45b298585058b66179a19729aa))
* register radarr-anime across fleet-tracking skill scripts ([db3347c](https://github.com/WhispersOfJ/media-stack/commit/db3347cdc628aa73f3144c359c5d01d3997730ea))
* remove restic backup system entirely ([cd841d6](https://github.com/WhispersOfJ/media-stack/commit/cd841d6a89eac6d9cbbaaec886657441c9402651))
* script to remove Radarr-orphaned empty movie folders ([55abc4f](https://github.com/WhispersOfJ/media-stack/commit/55abc4f3ba405c0e11b1e9e6d84c61c8fd386407))
* stand up sonarr-anime as a full peer instance to radarr-anime ([bb8b3e5](https://github.com/WhispersOfJ/media-stack/commit/bb8b3e54ebe82007bf6b94e7d0a786e5005d69bb))
* symlink installer for fish functions (Phase 8a) ([6fb8212](https://github.com/WhispersOfJ/media-stack/commit/6fb82120c5c0548bca8df426de7b49a051bd18e3))
* tracked-list registration + sync-tick endpoint for scheduled Letterboxd sync ([757493d](https://github.com/WhispersOfJ/media-stack/commit/757493d51cef2c04ec91ea71e3e0d4908f1afb8b))
* **trash-guides-applier:** add radarr-anime custom-format profile (dual audio, uncensored, LQ groups) ([82e2e91](https://github.com/WhispersOfJ/media-stack/commit/82e2e91d056eca4d00c86fa5b4d171f430b37f12))
* **trash-guides-applier:** add TRaSH custom-format converter script ([d6f0e43](https://github.com/WhispersOfJ/media-stack/commit/d6f0e43bbe94d57d33a4840184134a0e773ac973))
* **unpackerr:** wire radarr-anime as a second Radarr server ([68cc9f8](https://github.com/WhispersOfJ/media-stack/commit/68cc9f852ab7444782758b593b3c48e5f4d2cc8b))
* write the 4 fish functions commands.json already advertised (Phase 8a) ([66e93e2](https://github.com/WhispersOfJ/media-stack/commit/66e93e2be0a6aeba47710dd5d90c3bce4fecd1d8))


### Bug Fixes

* add missing Control Panel/radarr_anime vars to .env.example ([d16b12b](https://github.com/WhispersOfJ/media-stack/commit/d16b12bd358a3ee74818008e6bb8cc73b0062ba1))
* add missing RADARR_ANIME_API_KEY to cp_main_app test fixture ([0eb7281](https://github.com/WhispersOfJ/media-stack/commit/0eb7281e779cb2cc1739619ed80e22af2e8f8561))
* add missing tertiary nzbdav usenet vars to .env.example ([7bd400b](https://github.com/WhispersOfJ/media-stack/commit/7bd400ba0886c9614d4fed3fd6bee1ef44abe353))
* bump Pillow 11.3.0 -&gt; 12.3.0, clears 18 open Dependabot alerts ([7aa4e7e](https://github.com/WhispersOfJ/media-stack/commit/7aa4e7edbc02d4f3bc8da198af3e8bcaa53fc73d))
* **control-panel:** add login UI and static-file mount for evolved backend ([4b37554](https://github.com/WhispersOfJ/media-stack/commit/4b37554129aa49360c705b26312e8b0f5e2b4b30))
* **control-panel:** allow service-key auth on add-from-letterboxd-list ([d982fca](https://github.com/WhispersOfJ/media-stack/commit/d982fcaa1cd428cc9a2b1331bc7342cba3b03188))
* **control-panel:** don't let one unmatched file 500 a whole bulk import ([3711926](https://github.com/WhispersOfJ/media-stack/commit/37119266bc492c88a4dac783c3d158777523b3ce))
* **control-panel:** extend service-key auth to every fish-CLI-called route ([1437035](https://github.com/WhispersOfJ/media-stack/commit/14370357267554e7bc5625623f4a95b8d85f2625))
* **control-panel:** validate actual TCP source, not just spoofable Host header ([e360961](https://github.com/WhispersOfJ/media-stack/commit/e3609616cb240c579b1101eecbe2583fec81139d))
* **control-panel:** wire CONTROL_PANEL_SERVICE_API_KEY through to __stack_api.fish ([5809a63](https://github.com/WhispersOfJ/media-stack/commit/5809a631f10c04eac2700b304ab415174613f47e))
* **docker-compose-manager:** add radarr-anime to FUSE mount cascade dependents ([aa2f6a6](https://github.com/WhispersOfJ/media-stack/commit/aa2f6a6824ea5c2bf8a703b3579af6cbd5bc5dc0))
* green up Validate Compose and widen its lint/profile coverage ([e070b54](https://github.com/WhispersOfJ/media-stack/commit/e070b54a8852ecfac5f8baf6f6b93154916a0563))
* **health-monitor:** add 7 missing services to HTTP reachability check ([1c8c853](https://github.com/WhispersOfJ/media-stack/commit/1c8c853a591c141e61582ad98e2a5c1f931875c1))
* **kometa:** switch to manual-only runs ([784a579](https://github.com/WhispersOfJ/media-stack/commit/784a57924b307d2b7e68637c5728fb423d0f2962))
* lower nzbdav usenet connections to 25 per provider ([8feda56](https://github.com/WhispersOfJ/media-stack/commit/8feda56d3648d09001dfeaa3f6a351356903e029))
* **nzbdav_rclone:** remove --no-modtime, was poisoning Plex direct-play ([e031300](https://github.com/WhispersOfJ/media-stack/commit/e03130026901207ccd908de2bc3d6398ee1ba33d))
* **nzbdav:** add anime-movies to NZBDAV_CONFIG__API__CATEGORIES ([de1405b](https://github.com/WhispersOfJ/media-stack/commit/de1405b3629e1d6b61b99914dcb34978a79c0f1d))
* **nzbdav:** revert usenet MaxConnections back to 25/provider ([36d9a45](https://github.com/WhispersOfJ/media-stack/commit/36d9a45f37e66ceab8c1cdca0058ca84654064a9))
* raise nzbdav usenet connections to 50/provider, document DB deadlock ([3e81eed](https://github.com/WhispersOfJ/media-stack/commit/3e81eed3d5b55425d50a86979d02fb1c1851d5de))
* reconcile against the Plex API, not deleted_at (corrects a false positive) ([d799609](https://github.com/WhispersOfJ/media-stack/commit/d799609897956da6daeb95d27d987670400ddbac))
* remove tertiary nzbdav usenet provider ([f2f433b](https://github.com/WhispersOfJ/media-stack/commit/f2f433bd43aaef7ef7df7c1bc555cb80286f7cae))
* remove thundernews, set newshosting primary and ninja as backup ([d1b27b5](https://github.com/WhispersOfJ/media-stack/commit/d1b27b5cce17bb7cd994ea5d4e470ac4b01d9da7))
* repair drifted skill scripts and port 3 missing control-panel routes ([de6133f](https://github.com/WhispersOfJ/media-stack/commit/de6133f60f1bb07b269921bffbdae1e9680fc243))
* **request-manager-integrator:** resolve real container hostname, not app_name ([b13ce2d](https://github.com/WhispersOfJ/media-stack/commit/b13ce2dfd889190b33bcad56abf9c8159124e851))
* restore nzbdav usenet connections to 50 per provider ([553bde6](https://github.com/WhispersOfJ/media-stack/commit/553bde63edb1d0ef46d7b58e24ed24d79d47b0e6))
* self-heal stale FUSE mountpoint on nzbdav_rclone start ([5d43a0f](https://github.com/WhispersOfJ/media-stack/commit/5d43a0f4b7a1997438d43c5870b08d26bf9dd44d))
* send X-Api-Key from stack-* fish CLI commands ([e8fae06](https://github.com/WhispersOfJ/media-stack/commit/e8fae0606f37dd6efcdf2812a05395d64eb921e4))
* set all three nzbdav usenet providers to priority 0 ([172edfa](https://github.com/WhispersOfJ/media-stack/commit/172edfa3f7d850574307ef7043f14af409774142))
* **trash-guides-applier:** build real quality-profile items from schema, register radarr_anime ([c8aa4b5](https://github.com/WhispersOfJ/media-stack/commit/c8aa4b50dad54ffbe5b6b6a9bf20bc108e1d79ef))
* treat radarr_anime as a Radarr-type app in queue/import/blocklist paths ([eafa540](https://github.com/WhispersOfJ/media-stack/commit/eafa540a68c1b753246a74dbd33a918e42b49cd9))
* wire cleanuparr and seerr routers into main.py ([b5bf585](https://github.com/WhispersOfJ/media-stack/commit/b5bf58548214be629d232c4a84ab3fb3cd7e79d1))


### Performance Improvements

* raise NzbDAV provider MaxConnections 26 -&gt; 50 on both providers ([0d9c39f](https://github.com/WhispersOfJ/media-stack/commit/0d9c39fc32e493b519208f465afebc21213e7d65))

## [11.13.0](https://github.com/WhispersOfJ/media-stack/compare/v11.12.1...v11.13.0) (2026-08-02)


### Features

* add loop remediation toolkit for manual unmonitor/exclude ([9b9a697](https://github.com/WhispersOfJ/media-stack/commit/9b9a697ac8781f238c5503bafe5ddcb4663f7b37))
* promote queue-monitoring loop to stack-queue-autofix endpoint ([a6359f4](https://github.com/WhispersOfJ/media-stack/commit/a6359f4cf46e4151488b03ec46ddde1a2e26fc85))


### Bug Fixes

* add rclone timeout tuning to nzbdav_rclone mount, adopt larger cache ([9d6e93d](https://github.com/WhispersOfJ/media-stack/commit/9d6e93dea7349b1b2419f0d05c3553c5cc8aedc2))
* cap usenet provider connections at 25 each ([a05e09c](https://github.com/WhispersOfJ/media-stack/commit/a05e09c6a493c7a4eaeae5a0c215a8e63d5e284d))
* confirm Plex stalled_suspected over multiple polls before flagging ([ad12ad1](https://github.com/WhispersOfJ/media-stack/commit/ad12ad1c630c023196d86a4f76a3f936dc68aa50))
* docker-compose-manager cascade uses force-recreate, verifies mount ([77a95c2](https://github.com/WhispersOfJ/media-stack/commit/77a95c2a87e37fdd7ff8ca2149b99570c194bb29))
* fall back to direct API lookup when queue item's embedded monitored status is null ([1b05e3c](https://github.com/WhispersOfJ/media-stack/commit/1b05e3cbfa839944b0fc0af8aa59a7e09218e611))
* remove stale/phantom service references from control panel ([e1fc188](https://github.com/WhispersOfJ/media-stack/commit/e1fc188a6b189e94e1eb3fd45afdd8038368f650))
* skip re-search for unmonitored items in queue-autofix ([f959f3f](https://github.com/WhispersOfJ/media-stack/commit/f959f3fe61e35225a9324bce08699b9686adfe49))
* tolerate benign 404/timeout on queue-autofix blocklist delete ([0be5cb3](https://github.com/WhispersOfJ/media-stack/commit/0be5cb35b5204c6935762788dd656356e7614c51))

## [11.12.1](https://github.com/WhispersOfJ/media-stack/compare/v11.12.0...v11.12.1) (2026-07-31)


### Bug Fixes

* enable NzbDAV usenet cascade with explicit provider priority ([ae07f4e](https://github.com/WhispersOfJ/media-stack/commit/ae07f4e160a8e4428257ef7c5d7487872f70b066))
