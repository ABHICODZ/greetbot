#!/usr/bin/env bash

# GreetBot Raspberry Pi 5 Optimizer Script
# Run with: sudo ./pi_optimizer.sh

if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root (with sudo)." 
   exit 1
fi

echo "===================================================="
echo "          GREETBOT SYSTEM OPTIMIZER CORE            "
echo "===================================================="

# 1. Force CPU Governor to Performance (Maximum Clock Speed)
echo -n "[1/5] Setting CPU governor to performance... "
for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "$gov" ]; then
        echo "performance" > "$gov"
    fi
done
echo "DONE"
echo "Active CPU Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"

# 2. Minimize VM Swappiness (Pi 5 has 16GB RAM, prevent SD card read-write swap lags)
echo -n "[2/5] Adjusting virtual memory swappiness... "
sysctl vm.swappiness=1 >/dev/null
echo "DONE"
echo "vm.swappiness is now: $(sysctl -n vm.swappiness)"

# 3. Increase process limit and file descriptors for network/REST API performance
echo -n "[3/5] Increasing open files resource limits... "
ulimit -n 65535
echo "fs.file-max = 65535" >> /etc/sysctl.conf
sysctl -p >/dev/null 2>&1
echo "DONE"

# 4. Smart Process Killer (Terminate heavy background/desktop bloat)
echo "[4/5] Running smart process clean-up (killing GUI bloat if running)..."
BLOAT_PROCESSES=("chromium" "firefox" "webengine" "cups" "packagekitd" "gvfsd-trash")
for proc in "${BLOAT_PROCESSES[@]}"; do
    if pgrep -f "$proc" >/dev/null; then
        echo "  -> Terminating background $proc..."
        pkill -f "$proc"
    fi
done
echo "Clean-up complete."

# 5. Optimize Process Scheduling & Priorities
echo "[5/5] Re-prioritizing AI models & system threads..."
# Boost Ollama priority if running
OLLAMA_PID=$(pgrep -f "ollama serve")
if [ -n "$OLLAMA_PID" ]; then
    echo "  -> Found Ollama running (PID: $OLLAMA_PID). Boosting priority to nice -15."
    renice -n -15 -p "$OLLAMA_PID"
    # Also boost child processes of Ollama
    for child in $(pgrep -P "$OLLAMA_PID"); do
        renice -n -15 -p "$child"
    done
else
    echo "  -> Ollama service not running currently. Run: ollama serve"
fi

# Boost GreetBot python processes if running
ROBO_PIDS=$(pgrep -f "python3 robo_head.py")
if [ -n "$ROBO_PIDS" ]; then
    for pid in $ROBO_PIDS; do
        echo "  -> Found GreetBot Core (PID: $pid). Boosting priority to nice -10."
        renice -n -10 -p "$pid"
    done
else
    echo "  -> robo_head.py is not currently active. Boosting will apply when started."
fi

echo "===================================================="
echo "          OPTIMIZATION SYSTEM FULLY ARMED           "
echo "===================================================="
