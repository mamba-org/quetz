# Changelog

<!-- <START NEW CHANGELOG ENTRY> -->

## 0.6.0

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.5.0...822c9244f13c16d84ff44bd6492a6c2f48e9b4aa))

### Enhancements made

- Remove frontend [#565](https://github.com/mamba-org/quetz/pull/565) ([@wolfv](https://github.com/wolfv))

### Bugs fixed

- Fix upload endpoint [#597](https://github.com/mamba-org/quetz/pull/597) ([@simonbohnen](https://github.com/simonbohnen))
- Fix upload endpoint [#594](https://github.com/mamba-org/quetz/pull/594) ([@simonbohnen](https://github.com/simonbohnen))

### Maintenance and upkeep improvements

- Update check-release action to v2 [#601](https://github.com/mamba-org/quetz/pull/601) ([@janjagusch](https://github.com/janjagusch))
- Make `quetz` compatible with SQLAlchemy 2.0 [#598](https://github.com/mamba-org/quetz/pull/598) ([@simonbohnen](https://github.com/simonbohnen))
- Update pre-commit versions [#592](https://github.com/mamba-org/quetz/pull/592) ([@wolfv](https://github.com/wolfv))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-12-16&to=2023-02-16&type=c))

[@codecov-commenter](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Acodecov-commenter+updated%3A2022-12-16..2023-02-16&type=Issues) | [@janjagusch](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ajanjagusch+updated%3A2022-12-16..2023-02-16&type=Issues) | [@simonbohnen](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Asimonbohnen+updated%3A2022-12-16..2023-02-16&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-12-16..2023-02-16&type=Issues)

<!-- <END NEW CHANGELOG ENTRY> -->

## 0.5.0

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.4.4...7f77638aa4b94d6eeb3a18158ee6f9184061ef74))

### Enhancements made

- no file or directory mandatory [#558](https://github.com/mamba-org/quetz/pull/558) ([@brichet](https://github.com/brichet))
- Add an API for paginated package versions [#556](https://github.com/mamba-org/quetz/pull/556) ([@brichet](https://github.com/brichet))
- Implement multiple languages support for the TermsOfServices [#552](https://github.com/mamba-org/quetz/pull/552) ([@martinRenou](https://github.com/martinRenou))
- Adds a new endpoint to check if the user already signed the TOS [#548](https://github.com/mamba-org/quetz/pull/548) ([@hbcarlos](https://github.com/hbcarlos))
- Fix / consistent usage of f-strings [#538](https://github.com/mamba-org/quetz/pull/538) ([@riccardoporreca](https://github.com/riccardoporreca))
- Add upload endpoint [#533](https://github.com/mamba-org/quetz/pull/533) ([@atrawog](https://github.com/atrawog))
- Add SQL authenticator [#508](https://github.com/mamba-org/quetz/pull/508) ([@janjagusch](https://github.com/janjagusch))

### Bugs fixed

- Remove `httpx` pin, fix tests, & test plugins individually [#574](https://github.com/mamba-org/quetz/pull/574) ([@simonbohnen](https://github.com/simonbohnen))
- Fix sqlauth error parsing [#569](https://github.com/mamba-org/quetz/pull/569) ([@simonbohnen](https://github.com/simonbohnen))
- Fix update route in SQL Authenticator [#568](https://github.com/mamba-org/quetz/pull/568) ([@simonbohnen](https://github.com/simonbohnen))
- fix OpenAPI spec. by allowing "nullable" values [#564](https://github.com/mamba-org/quetz/pull/564) ([@kuepe-sl](https://github.com/kuepe-sl))
- fix package_versions.version_order database field after package version deletion [#562](https://github.com/mamba-org/quetz/pull/562) ([@kuepe-sl](https://github.com/kuepe-sl))
- fix path in HTML templates [#561](https://github.com/mamba-org/quetz/pull/561) ([@kuepe-sl](https://github.com/kuepe-sl))
- Fixes CI [#559](https://github.com/mamba-org/quetz/pull/559) ([@hbcarlos](https://github.com/hbcarlos))
- Fix/several typo errors [#557](https://github.com/mamba-org/quetz/pull/557) ([@brichet](https://github.com/brichet))
- Fixes issues and tests on indexes [#555](https://github.com/mamba-org/quetz/pull/555) ([@brichet](https://github.com/brichet))
- Remove an uploaded package whose filename does not match the package name [#554](https://github.com/mamba-org/quetz/pull/554) ([@brichet](https://github.com/brichet))
- Remove package from repodata.json [#551](https://github.com/mamba-org/quetz/pull/551) ([@brichet](https://github.com/brichet))
- channels with dots in their name cause a crash in indexing [#541](https://github.com/mamba-org/quetz/pull/541) ([@gabm](https://github.com/gabm))

### Maintenance and upkeep improvements

- Fixes CI [#559](https://github.com/mamba-org/quetz/pull/559) ([@hbcarlos](https://github.com/hbcarlos))
- Fixes issues and tests on indexes [#555](https://github.com/mamba-org/quetz/pull/555) ([@brichet](https://github.com/brichet))

### Other merged PRs

- Add docker badge to README [#547](https://github.com/mamba-org/quetz/pull/547) ([@dhirschfeld](https://github.com/dhirschfeld))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-05-19&to=2022-12-16&type=c))

[@atrawog](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Aatrawog+updated%3A2022-05-19..2022-12-16&type=Issues) | [@baszalmstra](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Abaszalmstra+updated%3A2022-05-19..2022-12-16&type=Issues) | [@brichet](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Abrichet+updated%3A2022-05-19..2022-12-16&type=Issues) | [@codecov-commenter](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Acodecov-commenter+updated%3A2022-05-19..2022-12-16&type=Issues) | [@dhirschfeld](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Adhirschfeld+updated%3A2022-05-19..2022-12-16&type=Issues) | [@gabm](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Agabm+updated%3A2022-05-19..2022-12-16&type=Issues) | [@hbcarlos](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ahbcarlos+updated%3A2022-05-19..2022-12-16&type=Issues) | [@janjagusch](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ajanjagusch+updated%3A2022-05-19..2022-12-16&type=Issues) | [@kuepe-sl](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Akuepe-sl+updated%3A2022-05-19..2022-12-16&type=Issues) | [@martinRenou](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3AmartinRenou+updated%3A2022-05-19..2022-12-16&type=Issues) | [@riccardoporreca](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ariccardoporreca+updated%3A2022-05-19..2022-12-16&type=Issues) | [@simonbohnen](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Asimonbohnen+updated%3A2022-05-19..2022-12-16&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-05-19..2022-12-16&type=Issues)

## 0.4.4

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.4.3...fb4bc9049dfd2de0233d8ae61dd5962e7e2b616e))

### Enhancements made

- improve logging [#534](https://github.com/mamba-org/quetz/pull/534) ([@wolfv](https://github.com/wolfv))
- Log post_index_creation exceptions [#532](https://github.com/mamba-org/quetz/pull/532) ([@atrawog](https://github.com/atrawog))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-05-11&to=2022-05-19&type=c))

[@atrawog](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Aatrawog+updated%3A2022-05-11..2022-05-19&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-05-11..2022-05-19&type=Issues)

## 0.4.3

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.4.2...42f9b9dca2f37058bc193fed890cd9524117576f))

### Enhancements made

- allow upload usage without conda-verify installed [#524](https://github.com/mamba-org/quetz/pull/524) ([@wolfv](https://github.com/wolfv))
- log errors of background tasks [#523](https://github.com/mamba-org/quetz/pull/523) ([@wolfv](https://github.com/wolfv))

### Bugs fixed

- fix compatibility with latest starlette [#530](https://github.com/mamba-org/quetz/pull/530) ([@wolfv](https://github.com/wolfv))
- fix proxy channels noarch and gzip repodata [#529](https://github.com/mamba-org/quetz/pull/529) ([@wolfv](https://github.com/wolfv))
- Fix PAM authentication log message [#526](https://github.com/mamba-org/quetz/pull/526) ([@riccardoporreca](https://github.com/riccardoporreca))
- fix mamba 0.23.0 compat [#525](https://github.com/mamba-org/quetz/pull/525) ([@wolfv](https://github.com/wolfv))
- Use infodata['size'] for s3fs [#521](https://github.com/mamba-org/quetz/pull/521) ([@atrawog](https://github.com/atrawog))

### Maintenance and upkeep improvements

- Move httpx as dependency [#507](https://github.com/mamba-org/quetz/pull/507) ([@fcollonval](https://github.com/fcollonval))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-04-07&to=2022-05-11&type=c))

[@atrawog](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Aatrawog+updated%3A2022-04-07..2022-05-11&type=Issues) | [@codecov-commenter](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Acodecov-commenter+updated%3A2022-04-07..2022-05-11&type=Issues) | [@fcollonval](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Afcollonval+updated%3A2022-04-07..2022-05-11&type=Issues) | [@riccardoporreca](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ariccardoporreca+updated%3A2022-04-07..2022-05-11&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-04-07..2022-05-11&type=Issues)

## 0.4.2

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.4.1...4c65023b11c1ee1bf4c3351429c9cb365e10b6ba))

### Bugs fixed

- Fix gcs region config entry [#517](https://github.com/mamba-org/quetz/pull/517) ([@janjagusch](https://github.com/janjagusch))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-04-06&to=2022-04-06&type=c))

[@janjagusch](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ajanjagusch+updated%3A2022-04-06..2022-04-06&type=Issues)

## 0.4.1

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.4.0...bd2d1fc0a8c99d90662645b9bf485f940ae06e8a))

### Enhancements made

- Make GCS bucket location configurable [#512](https://github.com/mamba-org/quetz/pull/512) ([@janjagusch](https://github.com/janjagusch))

### Maintenance and upkeep improvements

- Fix CI [#513](https://github.com/mamba-org/quetz/pull/513) ([@janjagusch](https://github.com/janjagusch))
- small test refactor, skip harvester tests on python 3.10 [#505](https://github.com/mamba-org/quetz/pull/505) ([@wolfv](https://github.com/wolfv))
- Unpin h2 [#500](https://github.com/mamba-org/quetz/pull/500) ([@janjagusch](https://github.com/janjagusch))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-03-14&to=2022-04-06&type=c))

[@codecov-commenter](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Acodecov-commenter+updated%3A2022-03-14..2022-04-06&type=Issues) | [@janjagusch](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ajanjagusch+updated%3A2022-03-14..2022-04-06&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-03-14..2022-04-06&type=Issues)

## 0.4.0

([Full Changelog](https://github.com/mamba-org/quetz/compare/v0.3.0...5f2832c0b39ef56c44c17a0460bc876ae350fae8))

### Enhancements made

- update all js [#501](https://github.com/mamba-org/quetz/pull/501) ([@wolfv](https://github.com/wolfv))
- attempt to fix CI [#497](https://github.com/mamba-org/quetz/pull/497) ([@wolfv](https://github.com/wolfv))
- Allow deleting channel members and changing role of existing members [#495](https://github.com/mamba-org/quetz/pull/495) ([@janjagusch](https://github.com/janjagusch))
- Bump url-parse from 1.4.7 to 1.5.10 in /quetz_frontend [#491](https://github.com/mamba-org/quetz/pull/491) ([@dependabot](https://github.com/dependabot))
- Make cache timeout for GCS configurable [#490](https://github.com/mamba-org/quetz/pull/490) ([@SophieHallstedtQC](https://github.com/SophieHallstedtQC))
- Bump follow-redirects from 1.11.0 to 1.14.8 in /quetz_frontend [#487](https://github.com/mamba-org/quetz/pull/487) ([@dependabot](https://github.com/dependabot))
- Bump ajv from 6.12.2 to 6.12.6 in /quetz_frontend [#486](https://github.com/mamba-org/quetz/pull/486) ([@dependabot](https://github.com/dependabot))
- Bump node-sass from 4.14.1 to 7.0.0 in /quetz_frontend [#485](https://github.com/mamba-org/quetz/pull/485) ([@dependabot](https://github.com/dependabot))
- Bump ssri from 6.0.1 to 6.0.2 in /quetz_frontend [#484](https://github.com/mamba-org/quetz/pull/484) ([@dependabot](https://github.com/dependabot))
- Bump postcss from 7.0.32 to 7.0.39 in /quetz_frontend [#482](https://github.com/mamba-org/quetz/pull/482) ([@dependabot](https://github.com/dependabot))

### Bugs fixed

- make mamba solver work with latest mamba release [#496](https://github.com/mamba-org/quetz/pull/496) ([@wolfv](https://github.com/wolfv))

### Maintenance and upkeep improvements

- fix some pytest and sqlalchemy warnings [#502](https://github.com/mamba-org/quetz/pull/502) ([@wolfv](https://github.com/wolfv))
- update all js [#501](https://github.com/mamba-org/quetz/pull/501) ([@wolfv](https://github.com/wolfv))

### Other merged PRs

- Bump path-parse from 1.0.6 to 1.0.7 in /quetz_frontend [#498](https://github.com/mamba-org/quetz/pull/498) ([@dependabot](https://github.com/dependabot))
- Bump lodash from 4.17.19 to 4.17.21 in /quetz_frontend [#483](https://github.com/mamba-org/quetz/pull/483) ([@dependabot](https://github.com/dependabot))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/mamba-org/quetz/graphs/contributors?from=2022-02-04&to=2022-03-14&type=c))

[@codecov-commenter](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Acodecov-commenter+updated%3A2022-02-04..2022-03-14&type=Issues) | [@dependabot](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Adependabot+updated%3A2022-02-04..2022-03-14&type=Issues) | [@janjagusch](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Ajanjagusch+updated%3A2022-02-04..2022-03-14&type=Issues) | [@SophieHallstedtQC](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3ASophieHallstedtQC+updated%3A2022-02-04..2022-03-14&type=Issues) | [@wolfv](https://github.com/search?q=repo%3Amamba-org%2Fquetz+involves%3Awolfv+updated%3A2022-02-04..2022-03-14&type=Issues)
