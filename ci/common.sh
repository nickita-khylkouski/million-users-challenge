# sourced by the ci/*.sh scripts: start_server ENV... / stop_server
SUB=${SUB:-$PWD/submissions/asm-epoll-nickita-khylkouski}
fresh_db() { psql -qX -d postgres -c "DROP DATABASE IF EXISTS $1 WITH (FORCE)" -c "CREATE DATABASE $1 TEMPLATE feed_seed" >/dev/null; }
start_server() {   # start_server PORT [VAR=VAL ...]: fresh database, server in the background, waits for /health
  local port=$1; shift
  fresh_db feed_ci
  ( cd "$SUB" && exec env DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/feed_ci \
      JWT_SECRET=million-users-challenge HOST=0.0.0.0 PORT=$port EXTRA_PORT=$((port + 1)) "$@" build/server ) \
      > /tmp/srv.log 2>&1 &
  SRV=$!
  for _ in $(seq 60); do curl -sf "http://127.0.0.1:$port/health" >/dev/null && break; sleep 0.5; done
  echo "-- server (env: ${*:-defaults}) start log:"; head -8 /tmp/srv.log
}
stop_server() { kill $SRV 2>/dev/null; wait $SRV 2>/dev/null; echo "-- server log tail:"; tail -4 /tmp/srv.log; }
