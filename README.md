# Herald

Exact-time mobile push notifications for [Logseq](https://logseq.com) tasks with
`SCHEDULED:`/`DEADLINE:` timestamps. A Python daemon scans the Syncthing-synced
Markdown on a NAS and pushes to a self-hosted [ntfy](https://ntfy.sh) server;
tapping a notification deep-links into the Logseq Android app. Work-folder reminders
are gated to working hours (Mon–Fri, configurable), excluding public holidays and
vacation days.

**Full design:** [SPEC.md](SPEC.md) (not being updated).

## Layout

Herald *is* this repo — the app lives at the root. `ntfy/` and `docs/` are support
folders.

| Path | What |
|---|---|
| [`app/`](app/) | The Herald daemon (Python package). |
| [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) | Build + run the daemon. |
| [`config.example.yaml`](config.example.yaml) | Copy to `config.yaml`; per-folder settings + gate profiles. |
| [`.env.example`](.env.example) | Copy to `.env`; secrets + host paths. |
| [`SPEC.md`](SPEC.md) | The complete Phase 1 design. |
| [`docs/ntfy-prerequisites.md`](docs/ntfy-prerequisites.md) | The contract Herald expects from ntfy (topics, tokens/ACL, network). |
| [`ntfy/`](ntfy/) | **Illustrative** example ntfy stack — not the authoritative deployment. |

ntfy is reusable infra meant to run from your own homelab/infra collection; this
repo only owns Herald and the integration contract.

## Deploy

The image is built by GitHub Actions on every `v*` tag and pushed to
`ghcr.io/kernicek/herald`. Deployment is a plain image pull (e.g. a Portainer
stack) — no build on the target.

```bash
# 0. Prereqs: a running ntfy (see docs/ntfy-prerequisites.md) + the shared network
docker network create ntfy-net

# 1. Config + secrets (place these where your deploy mounts them from)
cp config.example.yaml config.yaml     # edit ntfy_url: http://ntfy:80, graphs, gates
cp .env.example .env                    # NTFY_TOKEN, VACATION_ICAL_URL, GRAPHS_ROOT, DATA_PATH

# 2. Cut a release so CI publishes the image
git tag v0.1.0 && git push origin v0.1.0

# 3. Deploy the stack (pulls ghcr.io/kernicek/herald)
docker compose up -d
```

For **local development** instead of pulling, comment `image:` in
`docker-compose.yml` and use `build: .`.

Before trusting the scanner, prove the transport: post one message with
`Click: logseq://graph/Kernel?page=Test` and confirm the tap opens Logseq.

## Status

- **Phase 1 (this repo):** read-only Herald — scan, gate, defer/digest, push. Built.
- **Phase 2:** [Mark-done action button](https://github.com/kernicek/herald/issues/1) — deferred.

## License

Herald is free software licensed under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE). Copyright (C) 2026 Vojta Karen.

Distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
