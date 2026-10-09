#!/usr/bin/env bash
# Agentless file-level localization (LLM over the repository structure), one run.
# usage: ./run_agentless.sh <run_name> <model> [ids_file]
set -uo pipefail
cd "$(dirname "$0")"; . ./env.sh
RUN=$1; MODEL=$2; IDS=${3:-}
OUT=results/agentless/$RUN
mkdir -p "$OUT"
export PROJECT_FILE_LOC=$PWD/structures PYTHONPATH=$PWD/Agentless
args=(--file_level --output_folder "$OUT" --model "$MODEL" --backend anthropic --dataset "$PWD/data_105.jsonl" --num_threads 4 --skip_existing)
if [[ -n $IDS ]]; then
  while read -r id; do Agentless/.venv/bin/python Agentless/agentless/fl/localize.py "${args[@]}" --target_id "$id"; done < "$IDS"
else
  Agentless/.venv/bin/python Agentless/agentless/fl/localize.py "${args[@]}"
fi
