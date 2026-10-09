# Load the Anthropic key from the harness .env without echoing it.
set -a; . "${ENV_FILE:-../harness/.env}"; set +a
export PATH="$HOME/.local/bin:$PATH"
