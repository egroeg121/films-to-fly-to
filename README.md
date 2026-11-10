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

The landing page takes either a flight number (e.g. `BA286`) or a from/to
airport pair (3-letter IATA codes), plus a departure date, optional time and an
airline. It lists the supported airlines (the registry in
`src/films_to_fly_to/airlines.py`). A flight number's prefix selects the airline;
route searches use the airline dropdown.

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

## Static site on GitHub Pages

The ranked film list can be published as a static site (no server needed). The
`build-static` command fetches the BA catalog and OMDb ratings once and writes
`site/index.html` (client-side search, sort, genre and rating filters) plus
`site/films.json`:

```bash
OMDB_API_KEY=your_key_here uv run build-static [--out site]
```

The key is read from the environment at build time only; it is never written to
the output (the build aborts if it would be). The flight/date form from the
Docker app is not part of the static site, since the catalog is fleet-wide.

`.github/workflows/pages.yml` rebuilds and deploys on every push to `main`, monthly
(1st, 05:00 UTC) and on manual dispatch. One-time setup:

1. Add a repository secret `OMDB_API_KEY` (Settings > Secrets and variables > Actions).
2. Make the repo public (GitHub Pages on private repos needs a paid plan).
3. Settings > Pages > Source: **GitHub Actions**.

The Docker/FastAPI path above is unchanged.
