# Tools: building and testing the n8n recipes

These tools build every recipe's `n8n/workflow.json` and run its golden set.
You need them only to change a build or to rerun a golden set; to use a recipe, import its `workflow.json` (see the root README).

| Path | What it does |
|---|---|
| `builds/r<chapter>_<n>.py` | Describes one recipe's workflow, step by step as the book's build steps |
| `n8n/wf.py` | The builder: Config node, steps, AI step, key log, decision log, exception queue, stop flag |
| `n8n/golden.py` | Builds a recipe, imports a test copy into n8n, runs every golden case, writes `n8n/test-report.md` |
| `n8n/run-all.sh` | Runs every recipe's golden set in book order |
| `n8n/remote-test.sh` | Runs one recipe's golden set on a remote test stack over SSH |
| `mock-systems/server.py` | Stand-ins for the business systems; records calls, injects failures, passes AI calls through |
| `stack/docker-compose.yml` | The test stack: n8n 2.42.7, Postgres, the mock systems |
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
