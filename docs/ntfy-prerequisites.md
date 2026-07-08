# ntfy prerequisites (integration contract)

The notifier does **not** own the ntfy server — ntfy is reusable infra you deploy
separately (ideally from your homelab/infra compose collection, not this repo).

This document is the **contract** the notifier depends on. It is stable: it
describes *our* conventions (topics, tokens, network), not ntfy's internals. For
actually installing/configuring the ntfy server, follow the upstream docs — they
are the source of truth and stay current:

- Install & config: https://docs.ntfy.sh/install/
- Access control (users, tokens, ACL): https://docs.ntfy.sh/config/#access-control
- Config reference (`server.yml`): https://docs.ntfy.sh/config/

A minimal, **illustrative** compose + `server.yml` lives in [`../ntfy/`](../ntfy/)
as a starting point. Treat it as an example to adapt, not an authoritative
deployment — if it drifts from upstream, upstream wins.

## What the notifier requires

### 1. A shared Docker network

```bash
docker network create ntfy-net
```

The ntfy container joins `ntfy-net`; the notifier stack joins it as `external`.
This lets the notifier publish to ntfy **by container name, internally**, with no
tunnel/TLS hairpin.

### 2. Reachable URLs (two, by consumer)

| Consumer | URL | Why |
|---|---|---|
| Notifier (container) | `http://ntfy:80` | internal, over `ntfy-net`, fast |
| Phone (ntfy app) | `https://ntfy.example.com` | public, via Cloudflare tunnel, TLS |

The notifier's `global.ntfy_url` in `config.yaml` is the **internal** one.

### 3. Topics

- `logseq-personal` — personal-folder reminders
- `logseq-work` — work-folder reminders
- `logseq-admin` — diagnostics (feed-stale warnings, crashes, startup ping)

### 4. Two tokens, least privilege

Assuming `auth-default-access: "deny-all"` in `server.yml`:

```bash
# Publisher — used by the notifier container (write only)
ntfy user add notifier
ntfy access notifier 'logseq-*' write-only

# Subscriber — used by the phone (read only)
ntfy user add phone
ntfy access phone 'logseq-*' read-only

# Mint a token for each (put the notifier token in the notifier's env: NTFY_TOKEN)
ntfy token add notifier
ntfy token add phone
```

Run these inside the ntfy container, e.g.
`docker compose exec ntfy ntfy user add notifier`.

### 5. Timezone

Set `TZ=Europe/Prague` on the ntfy container so server-side timestamps match (the
notifier does its own tz-aware time math regardless).

## Summary of what this repo owns vs. not

| Owned here | Owned by your infra / upstream |
|---|---|
| The contract above | The running ntfy server |
| The notifier stack | ntfy image version, `server.yml` schema, volumes |
| An illustrative `ntfy/` example | The authoritative ntfy deployment |
