# Tools: building and testing the n8n and Make recipes

These tools build every recipe's `n8n/workflow.json` and `make/*.json` and run its golden set.
You need them only to change a build or to rerun a golden set; to use a recipe, import its build (see the root README).

| Path | What it does |
|---|---|
| `builds/r<chapter>_<n>.py` | Describes one recipe's workflow, step by step as the book's build steps |
| `n8n/wf.py` | The builder: Config node, steps, AI step, key log, decision log, exception queue, stop flag |
| `n8n/golden.py` | Builds a recipe, imports a test copy into n8n, runs every golden case, writes `n8n/test-report.md` |
| `n8n/run-all.sh` | Runs every recipe's golden set in book order |
| `n8n/remote-test.sh` | Runs one recipe's golden set on a remote test stack over SSH |
| `builds_make/r<chapter>_<n>.py` | Describes one recipe's Make scenarios, reusing the n8n build's rule JavaScript |
| `make/mk.py` | The Make builder: Config step, rules adapter, Retry and Skip handlers, key log, decision log, exception queue, stop flag |
| `make/golden_make.py` | Builds a recipe's blueprints, imports test copies into Make, runs the recipe's golden set, writes `make/test-report.md` |
| `make/remote-test.sh` | Runs one recipe's golden set on Make from a remote test stack over SSH |
| `mock-systems/server.py` | Stand-ins for the business systems; records calls, injects failures, passes AI calls through |
| `stack/docker-compose.yml` | The test stack: n8n 2.42.7, Postgres, the mock systems, PostgREST (the table API the Make builds use) |
| `changelog.py`, `status.py` | Generate `CHANGELOG.md` and every status line from the test reports |

## Run the golden sets yourself

1. Start the stack (see the comment at the top of `stack/docker-compose.yml`) and create the n8n owner account at http://127.0.0.1:5679.
2. In n8n, create an API key, a Postgres credential (host `postgres`, database and user `companion`), and an Anthropic credential with your own API key.
3. From the repository root:

```
export N8N_API_KEY=... PG_CREDENTIAL_ID=... ANTHROPIC_CREDENTIAL_ID=... AI_LIVE=1
python3 tools/n8n/golden.py R11.2
tools/n8n/run-all.sh
```

Cases marked `needs_ai` call the Anthropic API with your key; leave `AI_LIVE` unset to skip them.
A golden-set run is a test against stand-ins, not proof that a build works with your systems: connect your own and rerun the golden set with your data before go-live (book Chapter 16).

## Make

Make runs in Make's cloud, so it must reach the mock systems and the tables over the internet.

1. Publish the stack's mocks (port 5680) and PostgREST (port 5681) over HTTPS behind one long random path, such as `https://<host>/<secret>/` for the mocks and `https://<host>/<secret>/db/` for PostgREST, with the prefix stripped. Anything without the secret should get a 404. Remove the route when you finish testing.
2. In Make (a paid plan: the Code app is not on Free), create an API token with the scenarios, hooks and organization scopes.
3. From the repository root:

```
export MAKE_API_TOKEN=... MAKE_ZONE=us2.make.com MAKE_TEAM_ID=... MOCKS_PUBLIC_URL=https://<host>/<secret>
python3 tools/make/golden_make.py R11.2
```

Each run creates its scenarios and webhooks in your team and deletes them when it ends; the report lists the credits each case used (about 112 for R11.2).
