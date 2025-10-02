# BGP Route Collector Optimization Guide

## System Specifications
- **OS**: Debian (Virtual Machine)
- **CPU**: 4 VCPUs
- **IPv4**: 159 peers up, 45 down, 128,959,773 prefixes received
- **IPv6**: 160 peers up, 52 down, 32,250,660 prefixes received
- **BGP Software**: OpenBGPD

## Critical Memory Optimizations

With ~160M prefixes, substantial memory optimization is required:

### System Memory Configuration
Add to `/etc/sysctl.conf`:

```bash
# Critical for BGP memory management
vm.overcommit_memory = 1
vm.overcommit_ratio = 80
vm.swappiness = 1
vm.vfs_cache_pressure = 50
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# Increase memory mapping limits
vm.max_map_count = 1048576
kernel.shmmax = 17179869184
kernel.shmall = 4194304
```

## OpenBGPD-Specific Tuning

### BGP Configuration Optimizations
Add to `/etc/bgpd.conf`:

```bash
# Memory and performance tuning
socket "/var/run/bgpd.sock" restricted
holdtime min 9
log updates

# RIB optimization for large tables
rde rib Adj-RIB-In no evaluate
rde rib Loc-RIB rtable 0 fib-update no

# Connection management
tcp md5sig password "your_password" key-id 1
max-prefix 2000000 restart 60

# Process priority
nice-priority -10
```

## Network Stack Optimization

### High BGP Load Network Tuning
Add to `/etc/sysctl.conf`:

```bash
# Network tuning for 200+ BGP sessions
net.core.somaxconn = 32768
net.core.netdev_max_backlog = 10000
net.core.rmem_default = 1048576
net.core.rmem_max = 33554432
net.core.wmem_default = 1048576
net.core.wmem_max = 33554432

# TCP tuning for BGP sessions
net.ipv4.tcp_rmem = 8192 1048576 33554432
net.ipv4.tcp_wmem = 8192 1048576 33554432
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_probes = 3
net.ipv4.tcp_keepalive_intvl = 15

# IPv6 optimizations
net.ipv6.route.max_size = 2097152
```

## CPU Optimization for 4 VCPUs

**IMPORTANT**: OpenBGPD only uses 2 cores by default due to its architecture limitations. It has separate processes (RDE and SE) but doesn't scale to all CPU cores automatically.

### CPU Performance Settings

```bash
# Set CPU governor to performance
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### OpenBGPD Multi-Core Utilization

OpenBGPD has inherent limitations with multi-core usage:
- **Main process**: Parent daemon
- **RDE (Route Decision Engine)**: Handles route calculations
- **SE (Session Engine)**: Manages BGP sessions

#### Option 1: Manual Process Affinity (Recommended)

Pin different OpenBGPD processes to specific cores:

```bash
# Create script to pin BGP processes
cat > /usr/local/bin/bgp-cpu-affinity.sh << 'EOF'
#!/bin/bash
# Wait for bgpd to start
sleep 10

# Get all bgpd processes
MAIN_PID=$(pgrep -f "bgpd.*parent")
RDE_PID=$(pgrep -f "bgpd.*rde")
SE_PID=$(pgrep -f "bgpd.*session")

# Pin to different cores
if [ ! -z "$MAIN_PID" ]; then
    taskset -cp 0 $MAIN_PID
    echo "Main bgpd pinned to core 0: PID $MAIN_PID"
fi

if [ ! -z "$RDE_PID" ]; then
    taskset -cp 1-2 $RDE_PID
    echo "RDE bgpd pinned to cores 1-2: PID $RDE_PID"
fi

if [ ! -z "$SE_PID" ]; then
    taskset -cp 2-3 $SE_PID
    echo "SE bgpd pinned to cores 2-3: PID $SE_PID"
fi
EOF

chmod +x /usr/local/bin/bgp-cpu-affinity.sh
```

#### Option 2: SystemD Service Optimization

Create systemd override for bgpd:

```bash
systemctl edit bgpd
```

Add the following content:

```ini
[Service]
CPUAffinity=0-3
Nice=-5
IOSchedulingClass=1
IOSchedulingPriority=4
ExecStartPost=/usr/local/bin/bgp-cpu-affinity.sh
```

#### Option 3: Alternative BGP Software (if possible)

For better multi-core utilization, consider:
- **BIRD**: Better multi-threading support
- **FRRouting**: More modern architecture
- **GoBGP**: Go-based, naturally concurrent

### Monitoring CPU Usage per Process

```bash
# Monitor individual BGP processes
ps -eLf | grep bgpd

# Check CPU affinity
for pid in $(pgrep bgpd); do
    echo "PID $pid: $(taskset -cp $pid)"
done

# Monitor CPU usage by process
htop -p $(pgrep bgpd | tr '\n' ',' | sed 's/,$//')
```

## Process Limits Configuration

### Security Limits
Add to `/etc/security/limits.conf`:

```bash
bgpd soft nofile 32768
bgpd hard nofile 65536
bgpd soft memlock unlimited
bgpd hard memlock unlimited
bgpd soft nproc 4096
bgpd hard nproc 8192
```

### SystemD Limits
Add to `/etc/systemd/system.conf`:

```bash
DefaultLimitNOFILE=65536
DefaultLimitMEMLOCK=infinity
```

## VM-Specific Optimizations

### Service Optimization
Disable unnecessary services to free resources:

```bash
systemctl disable apt-daily.service
systemctl disable apt-daily.timer
systemctl disable apt-daily-upgrade.timer
systemctl disable systemd-resolved
systemctl disable ModemManager
systemctl disable bluetooth
```

### Kernel Parameters
Add to `/etc/default/grub`:

```bash
elevator=noop intel_idle.max_cstate=1 processor.max_cstate=1
```

Then update grub:

```bash
update-grub
```

## Memory Management Script

### BGP Memory Monitor
Create `/usr/local/bin/bgp-memory-monitor.sh`:

```bash
#!/bin/bash
BGP_PID=$(pgrep bgpd)
if [ ! -z "$BGP_PID" ]; then
    # Protect bgpd from OOM killer
    echo -500 > /proc/$BGP_PID/oom_score_adj

    # Monitor memory usage
    MEM_USAGE=$(ps -p $BGP_PID -o %mem --no-headers | tr -d ' ')
    if (( $(echo "$MEM_USAGE > 80" | bc -l) )); then
        logger "BGPd memory usage high: ${MEM_USAGE}%"
    fi
fi
```

Make it executable and add to cron:

```bash
chmod +x /usr/local/bin/bgp-memory-monitor.sh
echo "*/5 * * * * /usr/local/bin/bgp-memory-monitor.sh" | crontab -
```

## Monitoring Commands

### BGP Status Monitoring

```bash
# Check BGP memory usage
ps -p $(pgrep bgpd) -o pid,ppid,cmd,%mem,%cpu,rss

# Monitor active sessions
bgpctl show summary | head -20

# Check system load
vmstat 1 5

# Monitor network connections
ss -tuln | grep :179 | wc -l

# Check prefix counts
bgpctl show rib summary

# Monitor memory usage over time
watch -n 5 'ps -p $(pgrep bgpd) -o %mem,rss --no-headers'
```

## Expected Resource Usage

With your current load configuration:

- **Memory**: Expect 8-16GB RAM usage by bgpd process
- **CPU**: Likely 60-80% utilization across 4 cores during updates
- **Network**: Sustained 100-500 Mbps for route updates
- **Disk I/O**: Minimal unless logging extensively

## Emergency Procedures

### If System Becomes Unresponsive

```bash
# Temporarily reduce BGP sessions
bgpctl neighbor 192.168.1.1 down
bgpctl neighbor 2001:db8::1 down

# Clear system caches if needed
echo 3 > /proc/sys/vm/drop_caches

# Restart bgpd if necessary
systemctl restart bgpd
```

### Critical Monitoring Thresholds

- **Memory usage > 80%**: Consider adding more RAM or reducing sessions
- **CPU load > 90%**: May need additional vCPUs
- **BGP sessions down > 20%**: Check network connectivity and resource limits

## Implementation Steps

1. **Apply sysctl changes**:
   ```bash
   sysctl -p
   ```

2. **Restart services**:
   ```bash
   systemctl daemon-reload
   systemctl restart bgpd
   ```

3. **Verify optimizations**:
   ```bash
   bgpctl show summary
   ps aux | grep bgpd
   ```

4. **Monitor system for 24 hours** to ensure stability

## Performance Notes

- Your 4 vCPU setup is at the limit for this BGP scale
- Consider requesting additional CPU/memory resources if performance degrades
- Monitor OOM killer activity in `/var/log/syslog`
- BGP convergence times may be slower during high update periods

## Troubleshooting

### Common Issues

- **High memory usage**: Increase swap or reduce max-prefix limits
- **Session timeouts**: Adjust TCP keepalive settings
- **Slow convergence**: Check CPU affinity and nice values
- **OOM kills**: Increase vm.overcommit_ratio or add more RAM

### Log Monitoring

```bash
# Watch BGP logs
tail -f /var/log/daemon.log | grep bgpd

# Monitor system messages
journalctl -u bgpd -f

# Check for OOM events
dmesg | grep -i "killed process"
```
