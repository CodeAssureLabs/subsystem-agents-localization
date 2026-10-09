#!/usr/bin/env bash
# CoSIL file-level localization (iterative module call-graph search), one run.
# usage: ./run_cosil.sh <run_name> <litellm_model> [ids_file]
set -uo pipefail
cd "$(dirname "$0")"; . ./env.sh
RUN=$1; MODEL=$2; IDS=${3:-}
OUT=$PWD/results/cosil/$RUN
mkdir -p "$OUT"
# fl/ is on the path because CoSIL.py imports FL_prompt and FL_tools as top-level modules.
export PROJECT_FILE_LOC=$PWD/structures PYTHONPATH=$PWD/CoSIL:$PWD/CoSIL/CoSIL/fl
DATA=$PWD/data_105.jsonl; PY=$PWD/CoSIL/.venv/bin/python; cd CoSIL  # run as a module from the repo root (CoSIL/fl/CoSIL.py would shadow the package)
args=(--file_level --output_folder "$OUT" --model "$MODEL" --dataset "$DATA" --num_threads 4 --skip_existing)
if [[ -n $IDS ]]; then
  while read -r id; do "$PY" -m CoSIL.fl.CoSIL_localize_file "${args[@]}" --target_id "$id"; done < "../$IDS"
else
  "$PY" -m CoSIL.fl.CoSIL_localize_file "${args[@]}"
fi
