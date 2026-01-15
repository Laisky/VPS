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

### 4️⃣.5 Connection origin classification (kernel route based)
bold "📌 MongoDB Connection Origin Classification"

ss -tn | grep ":${MONGO_PORT}" \
  | awk '{print $5}' \
  | cut -d: -f1 \
  | sort \
  | uniq -c \
  | sort -nr \
  | while read -r count ip; do

    iface=$(ip route get "$ip" 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}')

    if [[ "$iface" =~ ^br-|^veth|^docker ]]; then
      origin="DOCKER"
    elif [[ "$iface" =~ ^tailscale ]]; then
      origin="EXTERNAL (TAILSCALE)"
    elif [[ "$iface" =~ ^eth|^ens|^enp ]]; then
      origin="EXTERNAL (PUBLIC)"
    elif [[ "$iface" == "lo" ]]; then
      origin="LOCAL HOST"
    else
      origin="UNKNOWN"
    fi

    printf "%-6s %-18s %-12s %-20s\n" \
      "$count" "$ip" "${iface:-N/A}" "$origin"
  done | awk '
BEGIN {
  printf "%-6s %-18s %-12s %-20s\n",
         "COUNT", "REMOTE_IP", "IFACE", "CLASSIFICATION"
}
{ print }
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
echo "- Audit clients with the highest connection counts for retry / pooling issues"
echo "- All Go clients must reuse a single mongo.Client and limit MaxPoolSize"

echo
bold "✔️ Dashboard complete"
