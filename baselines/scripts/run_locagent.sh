#!/usr/bin/env bash
# LocAgent localization (graph-guided agent, function calling, 2 samples merged by MRR).
# usage: ./run_locagent.sh <run_name> <litellm_model> [dataset_jsonl]
set -uo pipefail
cd "$(dirname "$0")"; . ./env.sh
RUN=$1; MODEL=$2; DATA=${3:-$PWD/data_105.jsonl}
OUT=$PWD/results/locagent/$RUN
mkdir -p "$OUT"
export GRAPH_INDEX_DIR=$PWD/index/graph BM25_INDEX_DIR=$PWD/index/bm25 PYTHONPATH=$PWD/LocAgent
PY=$PWD/LocAgent/.venv/bin/python; cd LocAgent
"$PY" auto_search_main.py --dataset "$DATA" --model "$MODEL" --localize --merge \
  --output_folder "$OUT" --num_processes ${NPROC:-8} --use_function_calling ${EXTRA:-}
