#!/usr/bin/env bash

set -euo pipefail

MONGO_PORT=27017
MONGO_CONTAINER_NAME="vps_mongodb6_1"

bold()   { echo -e "\033[1m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
sep()    { echo -e "\n────────────────────────────────────────────────────────────\n"; }

clear

bold "🧠 MongoDB Connection & Thread Status Dashboard"
echo "Time: $(date)"
sep

### 1️⃣ MongoDB thread / pids status
bold "📌 MongoDB Thread / PIDs Usage"

docker exec "$MONGO_CONTAINER_NAME" bash -c '
printf "%-25s %s\n" "ulimit -u:" "$(ulimit -u)"
printf "%-25s %s\n" "cgroup pids.max:" "$(cat /sys/fs/cgroup/pids.max 2>/dev/null || echo N/A)"
printf "%-25s %s\n" "cgroup pids.current:" "$(cat /sys/fs/cgroup/pids.current 2>/dev/null || echo N/A)"
'

MONGO_THREADS=$(ps -eLf | grep mongod | grep -v grep | wc -l)
printf "%-25s %s\n" "mongod threads:" "$MONGO_THREADS"

sep

### 2️⃣ MongoDB port connection overview
bold "📌 MongoDB Port Connection Overview (:${MONGO_PORT})"

TOTAL_CONN=$(ss -tn | grep ":${MONGO_PORT}" | wc -l || true)
printf "%-25s %s\n" "Current TCP connections:" "$TOTAL_CONN"

sep

### 3️⃣ Top source IPs
bold "📌 Top Source IPs"

ss -tn | grep ":${MONGO_PORT}" \
  | awk '{print $5}' \
  | cut -d: -f1 \
  | sort \
  | uniq -c \
  | sort -nr \
  | head -15 \
  | awk '{printf "%-10s %s\n", $1, $2}'

sep

### 4️⃣ IP → container mapping
bold "📌 IP → Docker Container Mapping"

docker ps -q | while read -r cid; do
  docker inspect "$cid" \
    --format '{{.Name}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
done | sed 's#^/##' | column -t

sep

### 4️⃣.5 Network Interface Classification (NEW)
bold "📌 MongoDB Connection Ingress Interfaces"

ss -tnp | grep ":${MONGO_PORT}" | awk '
{
  iface=$1
  remote=$5
  print iface, remote
}
' | sort | uniq -c | sort -nr | awk '
BEGIN {
  printf "%-6s %-12s %-22s %-20s\n",
         "COUNT", "IFACE", "REMOTE", "CLASSIFICATION"
}
{
  iface=$2
  remote=$3

  if (iface ~ /^veth|^br-|^docker/) {
    cls="DOCKER"
  } else if (iface ~ /^tailscale/) {
    cls="EXTERNAL (TAILSCALE)"
  } else if (iface ~ /^eth|^ens|^enp/) {
    cls="EXTERNAL (PUBLIC)"
  } else if (iface == "lo") {
    cls="LOCAL HOST"
  } else {
    cls="UNKNOWN"
  }

  printf "%-6s %-12s %-22s %-20s\n",
         $1, iface, remote, cls
}
'

sep
bold "🔍 Connection Storm Source Attribution"

# Collect all TCP connections touching MongoDB port
ss -tnp | grep ":${MONGO_PORT}" | awk '
{
  local=$4
  remote=$5
  pid=""
  proc=""
  if (match($0, /pid=([0-9]+)/, m)) pid=m[1]
  if (match($0, /users:\(\("([^"]+)"/, n)) proc=n[1]
  print remote, pid, proc
}
' | while read -r remote pid proc; do
  ip="${remote%:*}"
  port="${remote##*:}"

  # Determine if local or external
  if [[ "$ip" =~ ^(10\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.|192\.168\.) ]]; then
    origin="LOCAL"
  else
    origin="EXTERNAL"
  fi

  container="N/A"

  if [[ "$origin" == "LOCAL" && -n "$pid" && "$pid" != "-" ]]; then
    # Try to map PID to Docker container
    if [[ -f "/proc/$pid/cgroup" ]]; then
      cid=$(grep -oE '[0-9a-f]{64}' /proc/$pid/cgroup | head -1 || true)
      if [[ -n "$cid" ]]; then
        container=$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null | sed 's#^/##')
      fi
    fi
  fi

  printf "%-10s %-18s %-8s %-8s %-20s\n" \
    "$origin" "$ip:$port" "${pid:-N/A}" "${proc:-N/A}" "$container"
done | sort | uniq -c | sort -nr | head -20 | awk '
BEGIN {
  printf "%-6s %-10s %-22s %-8s %-8s %-20s\n",
         "COUNT", "ORIGIN", "REMOTE", "PID", "PROC", "CONTAINER"
}
{
  printf "%-6s %-10s %-22s %-8s %-8s %-20s\n",
         $1, $2, $3, $4, $5, $6
}
'

sep

### 5️⃣ Risk assessment
bold "🚨 Risk Assessment"

if docker exec "$MONGO_CONTAINER_NAME" bash -c 'cat /sys/fs/cgroup/pids.current 2>/dev/null' >/tmp/pids_current; then
  PC=$(cat /tmp/pids_current)
  PM=$(docker exec "$MONGO_CONTAINER_NAME" bash -c 'cat /sys/fs/cgroup/pids.max 2>/dev/null')

  if [[ "$PM" != "max" && "$PC" -gt $((PM * 90 / 100)) ]]; then
    red "⚠️  MongoDB is close to or has reached the pids limit; pthread_create will fail"
  else
    green "✅ pids usage is within a safe range"
  fi
fi

if ss -tn | grep ":${MONGO_PORT}" | grep -q docker-proxy; then
  red "⚠️  docker-proxy detected; published ports may amplify connection storms"
else
  green "✅ docker-proxy not detected"
fi

sep

bold "📎 Recommended Actions Summary"
echo "- If 'pthread_create failed' appears: restart the MongoDB container"
echo "- Ensure MongoDB is not exposed to the host via published ports"
echo "- Audit containers with the highest connection counts for Go client misuse"
echo "- All Go clients must reuse a single mongo.Client and limit MaxPoolSize"

echo
bold "✔️ Dashboard complete"
