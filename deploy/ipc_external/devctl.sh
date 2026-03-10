#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/../.. && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy/ipc_external"

if [[ ! -f "$DEPLOY_DIR/coala.env" ]]; then
  echo "Missing $DEPLOY_DIR/coala.env"
  echo "Run: cp $DEPLOY_DIR/coala.env.example $DEPLOY_DIR/coala.env"
  exit 1
fi

cmd="${1:-help}"

case "$cmd" in
  up)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" up -d --build
    ;;
  down)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" down
    ;;
  restart)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" restart
    ;;
  shell)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" exec coala-dev bash
    ;;
  run)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" exec coala-dev python main.py
    ;;
  test)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" exec coala-dev pytest -q
    ;;
  health)
    curl -sS --max-time 5 http://127.0.0.1:18081/health
    echo
    ;;
  status)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" ps
    ;;
  logs)
    docker compose -f "$DEPLOY_DIR/docker-compose.yml" logs -f --tail 100
    ;;
  *)
    cat <<'EOF'
Usage:
  deploy/ipc_external/devctl.sh up       # build/start dev container
  deploy/ipc_external/devctl.sh down     # stop/remove container
  deploy/ipc_external/devctl.sh shell    # open bash in container
  deploy/ipc_external/devctl.sh run      # run CoALA CLI
  deploy/ipc_external/devctl.sh test     # run pytest
  deploy/ipc_external/devctl.sh health   # check local model endpoint
  deploy/ipc_external/devctl.sh status   # docker compose ps
  deploy/ipc_external/devctl.sh logs     # follow logs
EOF
    ;;
esac
