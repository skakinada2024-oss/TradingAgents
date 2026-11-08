# Paper Trading Terminal

Local page for the in-process ledger in `tradingagents/paper_sim.py`. The page does not keep its own accounts. Dollars are virtual. `execution_permitted` stays false.

From the repository root, with the project virtualenv:

```bash
.venv/bin/python -m paper_terminal
```

Open http://127.0.0.1:8765/ . The process binds to loopback only. Ctrl-C stops it. It does not keep trading after you leave the page.

Choose Research Hold, Fixture round trip, or Scripted baseline, then Run simulation. Reset deletes that run's directory under `paper_terminal_runs/`. Download CSV and Download audit return the files the simulator wrote.

A preview bundle that does not include `.venv` is described in the run evidence. It needs Python 3.11+ and `python-dotenv` because importing the package loads `.env` if one is present. Do not put a key file next to the preview.
