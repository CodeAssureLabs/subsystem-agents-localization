# Published LLM localizers

Four published localization methods, each run three times on the 105 instances with Claude Haiku 4.5
(`claude-haiku-4-5`), the model of the domain-agent system. `../scripts/extract_runs.py` reads these outputs
into `../data/runs.json`; all scoring is done there, by the same rule as for every other method.

| Method | Source | Commit | What we run |
|---|---|---|---|
| Agentless (Xia et al., FSE 2025) | https://github.com/OpenAutoCoder/Agentless | `5ce5888` | file-level stage (`localize.py --file_level`), temperature 0 |
| CoSIL (Jiang et al., ASE 2025) | https://github.com/ZhonghaoJiang/CoSIL | `0568e42` | file-level stage (`CoSIL_localize_file`) |
| LocAgent (Chen et al., ACL 2025) | https://github.com/gersteinlab/LocAgent | `4935b55` | `auto_search_main.py --localize --merge --use_function_calling`, 2 samples; graph and BM25 indexes built with its own code (`build_locagent_index.py`) |
| Reformulate-Retrieve-Localize (Caumartin and Melo, BoatSE 2026) | no public code | n/a | reimplemented from the paper (`scripts/rrl.py`) |

## Inputs

`scripts/data_105.jsonl` holds the 105 instances in SWE-bench format (`instance_id`, `repo`, `base_commit`,
`problem_statement`, and an empty `patch`). Agentless and CoSIL read the repository structure produced by
`build_structures.py` (Agentless's own `create_structure`, applied to `git archive` of each base commit).
LocAgent's indexes are built from the same extractions.

## Changes to the published code

Only what was needed to run the tools on these instances with Haiku 4.5. The diffs are in `patches/`.

* **Agentless** (`patches/agentless.diff`): load instances from a local `.jsonl` file instead of the Hugging Face
  dataset, and accept the model names `claude-haiku-4-5` and `claude-sonnet-4-6`. Run with Python 3.13
  (the 2025/2026 Ansible code uses syntax that Python 3.11 cannot parse) and `anthropic<1`
  (the 1.x SDK rejects the `temperature` argument that Agentless passes).
* **CoSIL**: no code changes. Empty `__init__.py` files were added in `CoSIL/`, `CoSIL/fl/` and `CoSIL/util/`
  so that the package can be run as a module, and its hard-coded `./repo_structures` directory is a symlink
  to the structures built above.
* **LocAgent** (`patches/locagent.diff`):
  * load instances from a local `.jsonl` file; accept `anthropic/claude-haiku-4-5` and `anthropic/claude-sonnet-4-6`;
    add their prices to `util/cost_analysis.py`;
  * prompt caching (`cache_control` on the system prompt and the last message) and logging of cache-read and
    cache-write tokens; caching changes cost, not outputs;
  * `util/runtime/function_calling.py`: repair malformed tool arguments returned by Haiku (lists encoded as JSON
    strings, leaked `<parameter name=...>` markup, trailing commas), and `repo_ops.search_code_snippets` accepts a
    single string where a list is expected; `auto_search_main.py` catches `SyntaxError`/`NameError` when parsing
    tool output. Without these changes LocAgent stopped on many issues.
  * Environment: `litellm` 1.104 (the pinned 1.52.1 is no longer installable), CPU-only `torch`.
  * Empty outputs were rerun once with LocAgent's own `--rerun_empty_location`. One qutebrowser issue
    (`qutebrowser-54bcdc`) hung repeatedly in run 3 and counts as an empty prediction.
* **RRL** (`scripts/rrl.py`): an LLM extracts a JSON description of the issue; the query is explanation +
  identifiers + code snippets; BM25 (k1 = 0.9, b = 0.4, as Pyserini's default) over the non-test Python files at
  the base commit; an agent with `bm25_search` (top 20), `view_file` (first 512 whitespace tokens) and `submit`
  (5 files), followed by one self-validation turn; temperature 0; at most 25 turns. On 3 issues per run the
  context window was exceeded, and the last submitted answer is kept (`context_overflow` in the output).

## Results

`results/<method>/run{1,2,3}/`: `loc_outputs.jsonl` (predicted files and token usage per instance; for LocAgent
the merged ranking is in `merged_loc_outputs_mrr.jsonl`), `args.json`, and for LocAgent the compressed
trajectories `loc_trajs.jsonl.gz`.

## Running

The scripts expect the tool checkouts next to them (`Agentless/`, `CoSIL/`, `LocAgent/` at the commits above,
with the patches applied), bare clones of the three repositories (`ansible_bare`, `openlibrary_bare`,
`qutebrowser_bare`) one level up, and an `.env` file with `ANTHROPIC_API_KEY` (path in `ENV_FILE`).

```bash
python build_structures.py && python build_locagent_index.py
./run_agentless.sh run1 claude-haiku-4-5
./run_cosil.sh run1 anthropic/claude-haiku-4-5
./run_locagent.sh run1 anthropic/claude-haiku-4-5
python rrl.py run1 claude-haiku-4-5
```
