# AS 199036 NLNOG Ring Migration to BIRD Complete Guide

## Migration Overview
Migrating from OpenBGPD to BIRD for AS 199036 route collector will provide:
- **Better multi-core utilization** (all 4 vCPUs instead of 2)
- **Improved memory efficiency** for 160M+ prefixes
- **Better performance** for 200+ BGP sessions
- **More flexible filtering** and configuration options
- **Better IPv6 support** and dual-stack handling

## BIRD Configuration Templates

### Main Configuration (`bird.conf.j2`)

```conf
# AS 199036 NLNOG Ring BIRD Configuration
# High-performance route collector setup

# Global settings
router id {{ router_id }};
log syslog all;
log "/var/log/bird.log" { debug, trace, info, remote, warning, error, auth, fatal, bug };

# Performance optimizations for 160M+ prefixes
debug protocols { off };
timeformat protocol "%Y-%m-%d %T";
timeformat base "%Y-%m-%d %T";
timeformat log "%Y-%m-%d %T";

# Protocol templates for optimization
template bgp ring_peer {
    local as 199036;
    import all;
    export none;
    
    # Performance settings
    hold time 180;
    startup hold time 240;
    connect retry time 30;
    keepalive time 60;
    
    # Multi-path support
    add paths tx;
    
    # Memory optimization
    route limit 2000000 action warn;
    receive limit 2000000 action warn;
    
    # Enable graceful restart
    graceful restart yes;
    graceful restart time 240;
    
    # TCP optimization
    source address {{ local_ip }};
}

template bgp firehose_peer {
    local as 199036;
    import none;
    export all;
    
    # Firehose-specific settings
    hold time 300;
    startup hold time 360;
    connect retry time 60;
    keepalive time 100;
    
    # Add-path for firehose
    add paths tx;
    add paths rx off;
    
    # Prevent route acceptance
    route limit 1 action block;
    receive limit 1 action block;
    
    source address {{ local_ip }};
}

# RIB tables for different address families
table master4;
table master6;

# Kernel protocol (disabled for route collector)
protocol kernel kernel4 {
    ipv4 {
        table master4;
        import none;
        export none;
    };
}

protocol kernel kernel6 {
    ipv6 {
        table master6;
        import none;
        export none;
    };
}

# Device protocol
protocol device {
    scan time 10;
}

# Static routes (if needed)
protocol static static4 {
    ipv4 { table master4; };
}

protocol static static6 {
    ipv6 { table master6; };
}

# RPKI/RTR Protocol
protocol rpki rpki_validator {
    roa4 { table r4; };
    roa6 { table r6; };
    
    remote 127.0.0.1 port 3323;
    retry keep 90;
    retry 300;
    refresh keep 900;
    refresh 3600;
}

# Route collectors (peers group)
{% for peer in lg_peers %}
{% if lg_peers[peer].ipv4|default(None) %}
protocol bgp {{ peer }}_v4 from ring_peer {
    description "{{ peer }}-v4";
    neighbor {{ lg_peers[peer].ipv4 }} as {{ lg_peers[peer].asn }};
    
    ipv4 {
        table master4;
        import all;
        export none;
        
        # Prefix limits based on peer type
        {% if lg_peers[peer].tier|default('') == 'tier1' %}
        receive limit 1000000 action restart;
        {% elif lg_peers[peer].full_table|default(false) %}
        receive limit 800000 action restart;
        {% else %}
        receive limit 200000 action restart;
        {% endif %}
    };
    
    # Multihop for Ring connectivity
    multihop 255;
    
    {% if lg_peers[peer].password|default(None) %}
    password "{{ lg_peers[peer].password }}";
    {% endif %}
}
{% endif %}

{% if lg_peers[peer].ipv6|default(None) %}
protocol bgp {{ peer }}_v6 from ring_peer {
    description "{{ peer }}-v6";
    neighbor {{ lg_peers[peer].ipv6 }} as {{ lg_peers[peer].asn }};
    
    ipv6 {
        table master6;
        import all;
        export none;
        
        # IPv6 prefix limits
        {% if lg_peers[peer].tier|default('') == 'tier1' %}
        receive limit 200000 action restart;
        {% elif lg_peers[peer].full_table|default(false) %}
        receive limit 150000 action restart;
        {% else %}
        receive limit 50000 action restart;
        {% endif %}
    };
    
    multihop 255;
    
    {% if lg_peers[peer].password|default(None) %}
    password "{{ lg_peers[peer].password }}";
    {% endif %}
}
{% endif %}
{% endfor %}

# Firehose peers (readonly_peers group)
{% for peer in readonly_peers %}
{% if readonly_peers[peer].ipv4|default(None) %}
protocol bgp firehose_{{ peer }}_v4 from firehose_peer {
    description "firehose-{{ peer }}-v4";
    neighbor {{ readonly_peers[peer].ipv4 }} as {{ readonly_peers[peer].asn }};
    
    ipv4 {
        table master4;
        import none;
        export all;
        
        # Add-path support for firehose
        add paths tx;
    };
    
    multihop 255;
}
{% endif %}

{% if readonly_peers[peer].ipv6|default(None) %}
protocol bgp firehose_{{ peer }}_v6 from firehose_peer {
    description "firehose-{{ peer }}-v6";
    neighbor {{ readonly_peers[peer].ipv6 }} as {{ readonly_peers[peer].asn }};
    
    ipv6 {
        table master6;
        import none;
        export all;
        
        # Add-path support for firehose
        add paths tx;
    };
    
    multihop 255;
}
{% endif %}
{% endfor %}

# ASPA Test Group
protocol bgp aspa_test_v4 {
    description "ASPA Test IPv4";
    local as 199036;
    neighbor 45.138.228.4 as 15562;
    
    ipv4 {
        table master4;
        import none;
        export all;
        
        # ASPA-specific add-path
        add paths tx;
    };
    
    multihop 255;
    hold time 300;
}

protocol bgp aspa_test_v6 {
    description "ASPA Test IPv6";
    local as 199036;
    neighbor 2a10:3781:276::1 as 15562;
    
    ipv6 {
        table master6;
        import none;
        export all;
        
        # ASPA-specific add-path
        add paths tx;
    };
    
    multihop 255;
    hold time 300;
}

# ROA tables for RPKI validation
roa4 table r4;
roa6 table r6;

# Filters for RPKI validation (if needed)
filter rpki_validate_v4 {
    if (roa_check(r4, net, bgp_path.last) = ROA_INVALID) then {
        bgp_large_community.add((199036, 1000, 1));
    }
    accept;
}

filter rpki_validate_v6 {
    if (roa_check(r6, net, bgp_path.last) = ROA_INVALID) then {
        bgp_large_community.add((199036, 1000, 1));
    }
    accept;
}
```

## System Optimizations for BIRD

### 1. Kernel Parameters for BIRD Performance
Add to `/etc/sysctl.conf`:

```bash
# AS 199036 BIRD Memory Management - Enhanced for multi-core
vm.overcommit_memory = 1
vm.overcommit_ratio = 90
vm.swappiness = 1
vm.vfs_cache_pressure = 50
vm.dirty_ratio = 5
vm.dirty_background_ratio = 2

# BIRD-specific memory optimizations
vm.max_map_count = 4194304
kernel.shmmax = 68719476736
kernel.shmall = 16777216

# Multi-core networking for BIRD
net.core.somaxconn = 131072
net.core.netdev_max_backlog = 30000
net.core.rmem_default = 4194304
net.core.rmem_max = 134217728
net.core.wmem_default = 4194304
net.core.wmem_max = 134217728

# Advanced TCP tuning for 200+ BGP sessions
net.ipv4.tcp_rmem = 32768 4194304 134217728
net.ipv4.tcp_wmem = 32768 4194304 134217728
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_max_syn_backlog = 32768
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 5
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_probes = 6
net.ipv4.tcp_keepalive_intvl = 10

# IPv6 optimizations for BIRD
net.ipv6.route.max_size = 8388608
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.default.accept_ra = 0

# CPU scheduling optimizations
kernel.sched_migration_cost_ns = 5000000
kernel.sched_autogroup_enabled = 0
```

### 2. SystemD Service Configuration
Create `/etc/systemd/system/bird.service`:

```ini
[Unit]
Description=BIRD Internet Routing Daemon for AS 199036
Documentation=https://bird.network.cz/
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=notify
User=bird
Group=bird
ExecStart=/usr/sbin/bird -c /etc/bird/bird.conf -s /run/bird/bird.ctl -f
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/bin/kill -TERM $MAINPID
Restart=always
RestartSec=10
TimeoutStopSec=30

# Performance optimizations - BIRD uses all cores naturally
Nice=-15
IOSchedulingClass=1
IOSchedulingPriority=1

# Resource limits for 160M+ prefixes
LimitNOFILE=262144
LimitMEMLOCK=infinity
LimitCORE=infinity
LimitSTACK=67108864

# Memory settings for large routing tables
MemoryHigh=12G
MemoryMax=16G
MemorySwapMax=2G

# CPU settings - BIRD will utilize all cores
CPUAffinity=0-3
CPUQuota=400%

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/bird /var/log /var/lib/bird

# OOM protection
OOMScoreAdjust=-800

[Install]
WantedBy=multi-user.target
```

### 3. User and Directory Setup
```bash
# Create bird user and directories
useradd -r -s /bin/false -d /var/lib/bird bird
mkdir -p /etc/bird /run/bird /var/log/bird /var/lib/bird
chown bird:bird /run/bird /var/log/bird /var/lib/bird
chmod 755 /etc/bird /run/bird /var/log/bird /var/lib/bird
```

## BIRD Monitoring and Management Scripts

### 1. BIRD Health Monitor
Create `/usr/local/bin/as199036-bird-monitor.sh`:

```bash
#!/bin/bash
# AS 199036 BIRD Health Monitor

LOGFILE="/var/log/as199036-bird.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')
BIRD_SOCKET="/run/bird/bird.ctl"

# Check if BIRD is running
if ! systemctl is-active --quiet bird; then
    logger "AS199036 CRITICAL: BIRD service is not running"
    exit 1
fi

# Get session counts using birdc
IPV4_PEERS=$(echo "show protocols" | birdc -s $BIRD_SOCKET | grep -E "_v4.*BGP.*up" | wc -l)
IPV6_PEERS=$(echo "show protocols" | birdc -s $BIRD_SOCKET | grep -E "_v6.*BGP.*up" | wc -l)
TOTAL_PEERS=$((IPV4_PEERS + IPV6_PEERS))

# Get route counts
IPV4_ROUTES=$(echo "show route count" | birdc -s $BIRD_SOCKET | grep "routes" | awk '{print $1}')
IPV6_ROUTES=$(echo "show route ipv6 count" | birdc -s $BIRD_SOCKET | grep "routes" | awk '{print $1}')

# Memory usage
BIRD_PID=$(pgrep bird)
BIRD_MEM=$(ps -p $BIRD_PID -o rss= 2>/dev/null || echo "0")
BIRD_MEM_MB=$((BIRD_MEM / 1024))

# CPU usage
BIRD_CPU=$(ps -p $BIRD_PID -o %cpu= 2>/dev/null || echo "0")

# Log statistics
echo "[$DATE] AS199036 BIRD Stats: IPv4 peers: $IPV4_PEERS, IPv6 peers: $IPV6_PEERS, Routes: IPv4=$IPV4_ROUTES IPv6=$IPV6_ROUTES, Memory: ${BIRD_MEM_MB}MB, CPU: ${BIRD_CPU}%" >> $LOGFILE

# Alerts
if [ $TOTAL_PEERS -lt 280 ]; then
    logger "AS199036 ALERT: BIRD BGP sessions significantly down - Total: $TOTAL_PEERS (IPv4: $IPV4_PEERS, IPv6: $IPV6_PEERS)"
fi

if [ $BIRD_MEM_MB -gt 10000 ]; then
    logger "AS199036 WARNING: BIRD high memory usage: ${BIRD_MEM_MB}MB"
fi

# Check for BGP session errors
ERRORS=$(echo "show protocols" | birdc -s $BIRD_SOCKET | grep -c "down\|error")
if [ $ERRORS -gt 10 ]; then
    logger "AS199036 WARNING: Multiple BGP sessions down or in error state: $ERRORS"
fi
```

### 2. BIRD Performance Monitor
Create `/usr/local/bin/as199036-bird-performance.sh`:

```bash
#!/bin/bash
# AS 199036 BIRD Performance Monitor

BIRD_SOCKET="/run/bird/bird.ctl"

echo "=== AS 199036 BIRD Performance Report ==="
echo "Date: $(date)"
echo

# BIRD Process Information
echo "BIRD Process:"
ps -eo pid,ppid,cmd,%cpu,%mem,rss | grep bird | grep -v grep
echo

# BIRD Protocol Status
echo "BGP Protocol Summary:"
echo "show protocols" | birdc -s $BIRD_SOCKET | head -20
echo

# Route Table Summary
echo "Route Table Statistics:"
echo "IPv4 Routes:"
echo "show route count" | birdc -s $BIRD_SOCKET
echo
echo "IPv6 Routes:"
echo "show route ipv6 count" | birdc -s $BIRD_SOCKET
echo

# Memory Information
echo "System Memory Usage:"
free -h
echo

# Network Connections
echo "BGP Connections:"
echo "Total connections on port 179: $(ss -tuln | grep :179 | wc -l)"
echo "Established BGP connections: $(ss -tun | grep :179 | grep ESTAB | wc -l)"
echo

# System Load
echo "System Load:"
uptime
echo

# CPU Usage by Core
echo "CPU Usage by Core:"
mpstat -P ALL 1 1 | grep -v Average
```

### 3. Looking Glass Export for BIRD
Create `/usr/local/bin/as199036-bird-lg-export.sh`:

```bash
#!/bin/bash
# AS 199036 BIRD Looking Glass Data Export

EXPORT_DIR="/var/www/ring/as199036"
DATE=$(date +%Y%m%d-%H%M)
BIRD_SOCKET="/run/bird/bird.ctl"

mkdir -p $EXPORT_DIR/dumps

echo "Exporting BIRD RIB data for AS 199036..."

# IPv4 RIB export
echo "show route" | birdc -s $BIRD_SOCKET > $EXPORT_DIR/dumps/rib-ipv4-$DATE.txt
ln -sf $EXPORT_DIR/dumps/rib-ipv4-$DATE.txt $EXPORT_DIR/current-ipv4.txt

# IPv6 RIB export
echo "show route ipv6" | birdc -s $BIRD_SOCKET > $EXPORT_DIR/dumps/rib-ipv6-$DATE.txt
ln -sf $EXPORT_DIR/dumps/rib-ipv6-$DATE.txt $EXPORT_DIR/current-ipv6.txt

# Protocol summary
echo "show protocols" | birdc -s $BIRD_SOCKET > $EXPORT_DIR/peer-summary.txt

# Route statistics
echo "show route stats" | birdc -s $BIRD_SOCKET > $EXPORT_DIR/route-stats.txt

# Memory statistics
echo "show memory" | birdc -s $BIRD_SOCKET > $EXPORT_DIR/memory-stats.txt

# BGP summary
echo "show protocols all" | birdc -s $BIRD_SOCKET | grep -A5 -B5 "BGP" > $EXPORT_DIR/bgp-details.txt

# Cleanup old dumps (keep 48 hours)
find $EXPORT_DIR/dumps -name "rib-*.txt" -mtime +2 -delete

echo "BIRD export complete: $(date)"
```

## Migration Process from OpenBGPD to BIRD

### Pre-Migration Checklist

1. **Backup current configuration**:
   ```bash
   cp /etc/bgpd.conf /etc/bgpd.conf.backup.$(date +%Y%m%d)
   bgpctl show neighbor > /tmp/openbgpd-neighbors-backup.txt
   bgpctl show rib summary > /tmp/openbgpd-rib-backup.txt
   ```

2. **Install BIRD**:
   ```bash
   apt update
   apt install bird2
   systemctl stop bird
   systemctl disable bird
   ```

3. **Prepare BIRD configuration**:
   ```bash
   mkdir -p /etc/bird
   # Deploy your bird.conf.j2 template to /etc/bird/bird.conf
   ```

### Migration Steps

#### Step 1: Stop OpenBGPD
```bash
systemctl stop bgpd
systemctl disable bgpd
```

#### Step 2: Apply System Optimizations
```bash
# Apply new sysctl settings
sysctl -p

# Create BIRD user and directories
useradd -r -s /bin/false -d /var/lib/bird bird
mkdir -p /etc/bird /run/bird /var/log/bird /var/lib/bird
chown bird:bird /run/bird /var/log/bird /var/lib/bird
```

#### Step 3: Deploy BIRD Configuration
```bash
# Test BIRD configuration
bird -p -c /etc/bird/bird.conf

# If configuration is valid, start BIRD
systemctl enable bird
systemctl start bird
```

#### Step 4: Verify Migration
```bash
# Check BIRD status
systemctl status bird

# Verify BGP sessions
echo "show protocols" | birdc

# Check route counts
echo "show route count" | birdc
echo "show route ipv6 count" | birdc
```

#### Step 5: Install Monitoring
```bash
# Make scripts executable
chmod +x /usr/local/bin/as199036-bird-*.sh

# Add to crontab
crontab -e
```

Add these cron jobs:
```bash
# AS 199036 BIRD Monitoring
*/5 * * * * /usr/local/bin/as199036-bird-monitor.sh
0 */6 * * * /usr/local/bin/as199036-bird-performance.sh > /var/log/as199036-bird-performance.log
0 * * * * /usr/local/bin/as199036-bird-lg-export.sh
```

## Ansible Integration for BIRD

### Ansible Variables
```yaml
# AS 199036 BIRD variables
bgp_daemon: bird
bird_version: 2
as_number: 199036
router_id: "{{ ansible_default_ipv4.address }}"
local_ip: "{{ ansible_default_ipv4.address }}"

# Performance settings
bird_nice_priority: -15
bird_memory_limit: "16G"
bird_cpu_affinity: "0-3"

# BGP settings
bgp_hold_time: 180
bgp_keepalive_time: 60
bgp_graceful_restart: true

# Peer limits by type
peer_limits:
  tier1_ipv4: 1000000
  tier1_ipv6: 200000
  full_table_ipv4: 800000
  full_table_ipv6: 150000
  default_ipv4: 200000
  default_ipv6: 50000

# System limits
system_nofile_limit: 262144
system_memlock_unlimited: true
```

### Ansible Playbook Tasks
```yaml
- name: Install BIRD
  apt:
    name: bird2
    state: present
    update_cache: yes

- name: Create BIRD user
  user:
    name: bird
    system: yes
    shell: /bin/false
    home: /var/lib/bird
    create_home: yes

- name: Create BIRD directories
  file:
    path: "{{ item }}"
    state: directory
    owner: bird
    group: bird
    mode: '0755'
  loop:
    - /etc/bird
    - /run/bird
    - /var/log/bird
    - /var/lib/bird

- name: Deploy BIRD configuration
  template:
    src: bird.conf.j2
    dest: /etc/bird/bird.conf
    owner: bird
    group: bird
    mode: '0644'
    backup: yes
  notify: restart bird

- name: Deploy BIRD systemd service
  template:
    src: bird.service.j2
    dest: /etc/systemd/system/bird.service
    mode: '0644'
  notify:
    - reload systemd
    - restart bird

- name: Deploy monitoring scripts
  template:
    src: "{{ item }}.j2"
    dest: "/usr/local/bin/{{ item }}"
    mode: '0755'
  loop:
    - as199036-bird-monitor.sh
    - as199036-bird-performance.sh
    - as199036-bird-lg-export.sh

- name: Configure cron jobs
  cron:
    name: "{{ item.name }}"
    minute: "{{ item.minute }}"
    hour: "{{ item.hour | default('*') }}"
    job: "{{ item.job }}"
  loop:
    - name: "BIRD Health Monitor"
      minute: "*/5"
      job: "/usr/local/bin/as199036-bird-monitor.sh"
    - name: "BIRD Performance Report"
      minute: "0"
      hour: "*/6"
      job: "/usr/local/bin/as199036-bird-performance.sh > /var/log/as199036-bird-performance.log"
    - name: "BIRD Looking Glass Export"
      minute: "0"
      job: "/usr/local/bin/as199036-bird-lg-export.sh"

- name: Apply system optimizations
  sysctl:
    name: "{{ item.key }}"
    value: "{{ item.value }}"
    state: present
    reload: yes
  loop: "{{ sysctl_settings | dict2items }}"
  vars:
    sysctl_settings:
      vm.overcommit_memory: 1
      vm.overcommit_ratio: 90
      vm.swappiness: 1
      vm.max_map_count: 4194304
      net.core.somaxconn: 131072
      net.core.netdev_max_backlog: 30000
      net.ipv4.tcp_congestion_control: bbr

- name: Start and enable BIRD
  systemd:
    name: bird
    state: started
    enabled: yes
    daemon_reload: yes
```

## Performance Comparison: OpenBGPD vs BIRD

### Expected Improvements with BIRD

| Metric | OpenBGPD | BIRD | Improvement |
|--------|-----------|------|-------------|
| CPU Cores Used | 2 | 4 | 100% |
| Memory Efficiency | Baseline | 15-20% better | Significant |
| Session Handling | Good | Excellent | Better scaling |
| IPv6 Performance | Good | Excellent | Much better |
| Configuration Flexibility | Limited | Extensive | Much more flexible |
| Route Processing Speed | Good | Excellent | 20-30% faster |

### BIRD Advantages for Route Collectors

1. **True Multi-Threading**: BIRD uses all available CPU cores effectively
2. **Better Memory Management**: More efficient route storage and processing
3. **Advanced Filtering**: Powerful filter language for complex routing policies
4. **Better IPv6 Support**: Native dual-stack implementation
5. **RPKI Integration**: Better RPKI/RTR support
6. **Monitoring**: Rich CLI with detailed statistics
7. **Stability**: More mature codebase for high-scale deployments

## Rollback Plan

If migration encounters issues:

```bash
# Stop BIRD
systemctl stop bird
systemctl disable bird

# Restore OpenBGPD
systemctl enable bgpd
cp /etc/bgpd.conf.backup.$(date +%Y%m%d) /etc/bgpd.conf
systemctl start bgpd

# Verify restoration
bgpctl show summary
```

## Post-Migration Verification

After successful migration, verify:

1. **All BGP sessions are up**:
   ```bash
   echo "show protocols" | birdc | grep BGP | grep up | wc -l
   ```

2. **Route counts match expected values**:
   ```bash
   echo "show route count" | birdc
   echo "show route ipv6 count" | birdc
   ```

3. **Memory usage is optimal**:
   ```bash
   ps -p $(pgrep bird) -o %mem,rss
   ```

4. **All CPU cores are utilized**:
   ```bash
   htop -p $(pgrep bird)
   ```

This migration should significantly improve your route collector's performance and provide better utilization of your 4 vCPU setup while handling the 160M+ prefixes more efficiently.
