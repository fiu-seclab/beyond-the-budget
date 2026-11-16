# Beyond the Budget

Code and archived runs for an agent that pays a local memory service under a spending cap. Payments are simulated. No wallet, card, or chain is connected.

Figure scripts read the JSON in `data/` and write plots to `figures/`. They do not call a model.

## Layout

```
harness/     runners, the memory server, the local payment rail, scoring
data/        archived episode records
data/archive/   older records the figure scripts skip
figures/     output of scripts/reproduce.sh
scripts/     setup and figure regeneration
```

A record is named `priced_<model>_<policy>_<price>_<arm>.json`.

| Suffix | Contents |
| --- | --- |
| `_none_75_census2.json` | Limit stated in the prompt. One file per model. |
| `_per_charge_75_grid.json` | Wallet rejects a single charge over the cap. |
| `_cumulative_75_grid.json` | Wallet rejects a charge that would exceed the session total. |
| `_fbgeneric.json`, `_fbaware.json` | Same cumulative wallet, two different decline messages. |
| `oracle_affordability.json` | Retrieval check stored with the runs. The vector stores it was built from are not in the repo. |

Workspaces, wallet keys, virtualenvs, and API keys are not included. `harness/rescore_justified.py` rewrites the JSON in `data/`. The files already have those fields filled in.

## Regenerate the figures

Python 3.10 or newer. No API key.

```bash
bash scripts/setup.sh
bash scripts/reproduce.sh
```

That runs `harness/score_priced.py`, `rq1_figs.py`, `rq2_figs.py`, and `rq3_figs.py`. Tables print to the terminal. PDFs and `figures/tab-rq2-body.tex` are written under `figures/`.

From Git Bash on Windows, or without the shell scripts:

```bash
python harness/score_priced.py
python harness/rq1_figs.py
python harness/rq2_figs.py
python harness/rq3_figs.py
```

`scripts/setup.sh` installs `requirements.txt` into `.venv`. The figure scripts only import Matplotlib. mem0, Qdrant, and FastEmbed are in the same file because a new episode needs them.

## Run a new episode

This calls OpenRouter and will not match an archived trace. The memory client is started with `harness/.venv-mem0`, and that path is a Linux virtualenv (`bin/python`).

```bash
python -m venv harness/.venv-mem0
harness/.venv-mem0/bin/pip install -r requirements.txt
export OPENROUTER_API_KEY=...    # do not commit this

python harness/x402_rail.py 8402
python harness/priced_probe.py --model meta-llama/llama-4-scout \
  --price 0.75 --cap 5.00 --policy none --n 20 --arm census2
```

`--policy` is `none`, `per_charge`, or `cumulative`. The probe writes `data/priced_<model>_<policy>_<price>_<arm>.json` and refuses to replace a file that is already there. Pass `--out` to write somewhere else. The rail binds to `127.0.0.1`.

## Scripts

| Command | Role |
| --- | --- |
| `harness/priced_probe.py` | One cell: model, policy, price, episode count. |
| `harness/x402_rail.py` | Local wallet and facilitator. Argument is the port. |
| `harness/mem_client.py` | Command the agent is allowed to run: `search` or `pay`. |
| `harness/mcp_memory_priced.py` | Memory server. Bills per memory returned. |
| `harness/stage_priced.py` | Builds one episode's memory store and wallet policy. |
| `harness/task_sampler.py` | Builds a task from an episode id. |
| `harness/score_priced.py` | Prints summary tables from `data/`. |
| `harness/rq1_figs.py`, `rq2_figs.py`, `rq3_figs.py` | Write the plots. |

Other files in `harness/` are from earlier pilots. `scripts/reproduce.sh` does not call them.
