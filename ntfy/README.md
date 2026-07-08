# ntfy/ — illustrative example only

This is a **runnable starting point**, not the authoritative ntfy deployment.

- ntfy is reusable infra — deploy the real server from your homelab/infra compose
  collection, so its lifecycle isn't tied to this project.
- The **binding contract** the notifier depends on (topics, tokens/ACL, the
  `ntfy-net` network, the internal `http://ntfy:80` URL) lives in
  [`../docs/ntfy-prerequisites.md`](../docs/ntfy-prerequisites.md). That doc is
  stable across ntfy version changes.
- For the current image, `server.yml` schema, and volume layout, **upstream is the
  source of truth**: https://docs.ntfy.sh/

If this example ever drifts from upstream, it's a convenience nuisance — not a
broken dependency, because the notifier only relies on the contract doc.

## Quick start (example)

```bash
docker network create ntfy-net          # once, shared with the notifier stack

# Create the three subfolders on your TrueNAS dataset and make them writable by the
# uid:gid the container runs as (the `user:` in docker-compose.yml):
mkdir -p /mnt/POOL/DATASET/etc /mnt/POOL/DATASET/cache /mnt/POOL/DATASET/lib
chown -R 1000:1000 /mnt/POOL/DATASET/etc /mnt/POOL/DATASET/cache /mnt/POOL/DATASET/lib

# Config lives IN the mounted config dir (upstream mounts /etc/ntfy as a directory,
# not a single file). Copy this repo's server.yml in as your starting point:
cp server.yml /mnt/POOL/DATASET/etc/server.yml

docker compose up -d
# then create users/tokens/ACL per ../docs/ntfy-prerequisites.md
```

Notes:
- **`server.yml` goes in the `etc/` config dir on the dataset**, because we mount
  the whole `/etc/ntfy` directory (upstream's pattern). The copy in this repo is the
  tracked source of truth — edit it here, re-copy on change (or deploy from git so
  the dataset never becomes a competing copy).
- Replace `POOL/DATASET` and set `user:` to match your dataset's owner. On TrueNAS
  you can instead set ownership via the dataset's **Edit Permissions** in the UI.
- One dataset with `etc/`, `cache/`, `lib/` subfolders is fine — no separate
  datasets needed. These are bind mounts, so they are **not** declared in a
  top-level `volumes:` section.
- `/var/lib/ntfy` (auth DB) must be persisted because we use auth (`deny-all` +
  tokens); upstream's minimal no-auth example omits it.
- The official ntfy image uses the standard `user:` directive — not LinuxServer
  `PUID`/`PGID`.
