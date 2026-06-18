# films-to-fly-to
Get the latest films from airlines and rank them by how good they are

## Running with Docker

### Setup

```bash
cp .env.example .env
# Edit .env and set your OMDB API key:
echo 'OMDB_API_KEY=your_key_here' >> .env
```

### Start the server

```bash
docker compose up -d
```

The server is now accessible at http://localhost:8000.

### Access from any Tailscale device

The host's Tailscale connection exposes port 8000 to all your Tailscale devices automatically.

Find your Tailscale IP:

```bash
tailscale ip -4
```

Then open `http://<tailscale-ip>:8000` from any device on your Tailscale network (e.g. your phone).

### Monthly catalog snapshot (cron on host)

The snapshot cron runs on the host, not inside the container:

```bash
# Add to crontab (runs first of each month at 3am):
0 3 1 * * cd /path/to/films_to_fly_to && docker compose exec web uv run catalog-snapshot
```

### Notes

- The cache database is stored in a Docker volume (`ftft-data`) and persists across container restarts
- `.env` is gitignored — never commit your API key
- No Tailscale container is needed; host Tailscale already exposes the port
