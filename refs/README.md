# Local reference clones

Shallow (`--depth 1`) clones of the two external projects this repo builds on,
kept for offline reading. The clones themselves are **not tracked** by this repo
(see `.gitignore`); only this manifest is. Re-create them with the commands below.

| Project | Local path | Commit | Date | License |
|---|---|---|---|---|
| [Magid-William/Articles](https://github.com/Magid-William/Articles) | `refs/Magid-William-Articles` | `ca20200cc23f07ba4982c44b2f66e9102aafe00d` | 2026-09-05 | none stated |
| [badjeff/ads1220-zephyr-module](https://github.com/badjeff/ads1220-zephyr-module) | `refs/badjeff-ads1220-zephyr-module` | `73987bc6379fb68b67cc1e22a06333db2c014d23` | 2026-07-14 | Apache-2.0 |

The relevant file in `Magid-William-Articles` is `TrackPoint/README.md`.
Clone date: 2026-09-30.

Findings are summarised in `AGENTS.md` → "Reference projects".

## Re-clone

```sh
git clone --depth 1 https://github.com/Magid-William/Articles refs/Magid-William-Articles
git clone --depth 1 https://github.com/badjeff/ads1220-zephyr-module refs/badjeff-ads1220-zephyr-module
```

## Licensing note

`Magid-William/Articles` states no license; its content is used here for
reference only and is deliberately not committed. `badjeff/ads1220-zephyr-module`
is Apache-2.0.
