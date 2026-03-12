# DDoS-Guard: Technical Implementation Plan

## Executive Summary

Simplified DDoS detection and mitigation system leveraging existing Akvorado infrastructure with ClickHouse.

**Infrastructure:**
- Existing Akvorado flow collector (sFlow from Arista switches)
- Existing ClickHouse database with flow data
- Existing BIRD 2.x routing daemon on VPP routers
- 10 Gbps capacity

**Key Features:**
- ClickHouse-based detection queries
- Automatic BIRD configuration generation
- Multi-tier mitigation (Flowspec selective filtering + RTBH blackhole)
- Webhook alerting
- Sub-minute detection latency

---

## System Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXISTING INFRASTRUCTURE                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │ Arista sFlow │  │  Akvorado    │  │  ClickHouse  │                       │
│  │   Export     │──▶│  Collector   │──▶│   Database   │                       │
│  └──────────────┘  └──────────────┘  └──────┬───────┘                       │
└─────────────────────────────────────────────┼────────────────────────────────┘
                                              │
                                              │ (remote connection)
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DDOS-GUARD (BIRD Server)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │   Python    │───▶│   BIRD      │───▶│   VPP       │                     │
│  │   Script    │    │   Config    │    │  Routers    │                     │
│  │ (Detection) │    │  (Flowspec) │    │ (Blackhole) │                     │
│  └──────┬──────┘    └─────────────┘    └─────────────┘                     │
│         │                                                                   │
│         ▼                                                                   │
│  ┌───────────────┐                                                         │
│  │   Webhook     │                                                         │
│  │   Alerts      │                                                         │
│  └───────────────┘                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction

```
ClickHouse Query (every 60s)
       │
       ▼
┌─────────────┐
│  Detection  │──▶ Check thresholds:
│   Engine    │    • >1 Gbps general
└──────┬──────┘    • >200 Mbps UDP
       │          • >100 Mbps + 20 sources
       │          • >100 Mbps + 10 countries
       ▼
┌─────────────┐
│  Generate   │──▶ Create BIRD config files:
│   Configs   │    • v4-flowspec.conf
└──────┬──────┘    • v6-flowspec.conf
       │          • v4-blackhole.conf
       │          • v6-blackhole.conf
       ▼
┌─────────────┐
│   Compare   │──▶ Check if configs changed
│   & Apply   │
└──────┬──────┘
       │
       ├─ No change ──▶ Wait next cycle
       │
       ▼
┌─────────────┐
│  birdc      │──▶ Reload BIRD configuration
│ configure   │
└─────────────┘
       │
       ▼
┌─────────────┐
│   Webhook   │──▶ Send alert notification
│   Alert     │
└─────────────┘
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Detection | Python 3.8+ | Query ClickHouse, generate configs |
| Database | ClickHouse | Flow storage and aggregation |
| Routing | BIRD 2.0+ | RTBH and Flowspec announcement |
| Data Plane | VPP 24+ | High-performance forwarding |

### Python Dependencies

```txt
clickhouse-driver>=0.2.0    # ClickHouse connectivity
pyyaml>=6.0                  # Configuration parsing
requests>=2.28.0             # Webhook alerting
```

---

## Data Models

### Detection Event

```python
{
    "timestamp": "2026-03-12T14:30:00Z",
    "target_ip": "203.0.113.10",
    "protocol": "UDP",
    "src_port": 53,
    "gbps": 1.234,
    "mpps": 0.456,
    "sources": 45,
    "countries": 12,
    "packet_size": {
        "p10": 1476,
        "p90": 1500
    }
}
```

### BIRD Flowspec Rule

```
route flow4 {
  dst 203.0.113.10/32;
  sport = 53;
  length >= 1476 && <= 1500;
  proto = 17;
}{
  bgp_ext_community.add((generic, 0x80060000, 0x00000000));
};
```

### BIRD Blackhole Rule

```
route 203.0.113.10/32 blackhole {
  bgp_community.add((65535, 666));
};
```

---

## Detection Logic

### ClickHouse Schema

```sql
-- Pre-aggregated DDoS detection table
CREATE TABLE IF NOT EXISTS ddos_logs (
  TimeReceived DateTime,
  DstAddr IPv6,
  Proto UInt32,
  SrcPort UInt16,
  Gbps SimpleAggregateFunction(sum, Float64),
  Mpps SimpleAggregateFunction(sum, Float64),
  sources AggregateFunction(uniqCombined(12), IPv6),
  countries AggregateFunction(uniqCombined(12), FixedString(2)),
  size AggregateFunction(quantiles(0.1, 0.9), UInt64)
) ENGINE = SummingMergeTree
PARTITION BY toStartOfHour(TimeReceived)
ORDER BY (TimeReceived, DstAddr, Proto, SrcPort)
TTL toStartOfHour(TimeReceived) + INTERVAL 6 HOUR DELETE;

-- Materialized view for real-time aggregation
CREATE MATERIALIZED VIEW ddos_logs_view TO ddos_logs AS
  SELECT
    toStartOfMinute(TimeReceived) AS TimeReceived,
    DstAddr,
    Proto,
    SrcPort,
    sum(((((Bytes * SamplingRate) * 8) / 1000) / 1000) / 1000) / 60 AS Gbps,
    sum(((Packets * SamplingRate) / 1000) / 1000) / 60 AS Mpps,
    uniqCombinedState(12)(SrcAddr) AS sources,
    uniqCombinedState(12)(SrcCountry) AS countries,
    quantilesState(0.1, 0.9)(toUInt64(Bytes/Packets)) AS size
  FROM flows
  WHERE DstNetRole = 'customers'
  GROUP BY TimeReceived, DstAddr, Proto, SrcPort;
```

### Detection Query

```sql
SELECT *
FROM (
  SELECT
    TimeReceived,
    DstAddr,
    dictGetOrDefault('protocols', 'name', Proto, '???') AS Proto,
    SrcPort,
    sum(Gbps) AS Gbps,
    sum(Mpps) AS Mpps,
    uniqCombinedMerge(12)(sources) AS sources,
    uniqCombinedMerge(12)(countries) AS countries,
    quantilesMerge(0.1, 0.9)(size) AS size
  FROM ddos_logs
  WHERE TimeReceived > now() - INTERVAL 60 MINUTE
  GROUP BY TimeReceived, DstAddr, Proto, SrcPort
)
WHERE (Gbps > 1.0)
   OR ((Proto = 'UDP') AND (Gbps > 0.2))
   OR ((sources > 20) AND (Gbps > 0.1))
   OR ((countries > 10) AND (Gbps > 0.1))
ORDER BY TimeReceived DESC, Gbps DESC
```

### Threshold Configuration

```yaml
detection:
  interval_seconds: 60
  max_rules: 20

  thresholds:
    gbps: 1.0                    # 1 Gbps general threshold
    udp_gbps: 0.2                # 200 Mbps for UDP
    gbps_with_sources: 0.1       # 100 Mbps with many sources
    min_sources: 20              # Minimum unique sources
    gbps_with_countries: 0.1     # 100 Mbps with many countries
    min_countries: 10            # Minimum source countries
```

---

## Mitigation Strategy

### Dual-Mode Approach

1. **Flowspec (Primary)** - Selective filtering
   - Filter specific attack patterns (port, packet size)
   - Preserves legitimate traffic to target
   - Applied first for all attacks

2. **RTBH (Emergency)** - Full blackhole
   - Sacrifice target to protect network
   - Applied when attack exceeds 5 Gbps
   - Upstream community propagation

### Rule Generation Logic

```python
def generate_rules(detection_result):
    # Always generate Flowspec rule
    flowspec_rule = {
        "type": "flowspec",
        "target": detection_result["target_ip"],
        "protocol": detection_result["protocol"],
        "src_port": detection_result["src_port"],
        "packet_size": detection_result["packet_size"],
        "action": "drop"  # Rate-limit to 0
    }

    # Generate RTBH rule for high-volume attacks
    if detection_result["gbps"] > 5.0:
        blackhole_rule = {
            "type": "blackhole",
            "target": detection_result["target_ip"],
            "community": "65535:666"
        }
        return [flowspec_rule, blackhole_rule]

    return [flowspec_rule]
```

---

## BIRD Configuration

### Base Configuration

```
# /etc/bird/bird.conf

log stderr all;
router id 192.0.2.1;

protocol device {
    scan time 10;
}

# Include generated DDoS configs
include "/etc/bird/ddos/v4-flowspec.conf";
include "/etc/bird/ddos/v6-flowspec.conf";
include "/etc/bird/ddos/v4-blackhole.conf";
include "/etc/bird/ddos/v6-blackhole.conf";

# Flowspec tables
flow4 table flowtab4;
flow6 table flowtab6;

# Blackhole route table
ro table ddos_blackhole;

# BGP exporter to VPP routers
protocol bgp exporter {
    flow4 {
        import none;
        export where proto = "flowspec4";
    };
    flow6 {
        import none;
        export where proto = "flowspec6";
    };
    ipv4 {
        import none;
        export where proto = "blackhole4";
    };
    ipv6 {
        import none;
        export where proto = "blackhole6";
    };
    local as 64666;
    neighbor range 192.0.2.0/24 external;
    multihop;
    dynamic name "exporter";
    dynamic name digits 2;
    graceful restart yes;
    graceful restart time 0;
    long lived graceful restart yes;
    long lived stale time 3600;
}

# Static protocols for generated rules
protocol static flowspec4 {
    flow4;
    # Rules generated by ddos-guard script
}

protocol static flowspec6 {
    flow6;
    # Rules generated by ddos-guard script
}

protocol static blackhole4 {
    ro table ddos_blackhole;
    # Rules generated by ddos-guard script
}

protocol static blackhole6 {
    ipv6;
    # Rules generated by ddos-guard script
}
```

### Generated File Format

**v4-flowspec.conf:**
```
# Time: 2026-03-12T14:30:00Z
# Source: 203.0.113.10, protocol: UDP, port: 53
# Gbps/Mpps: 1.234/0.456, packet size: 1476<=X<=1500
# Sources: 45, countries: 12

route flow4 {
  dst 203.0.113.10/32;
  sport = 53;
  length >= 1476 && <= 1500;
  proto = 17;
}{
  bgp_ext_community.add((generic, 0x80060000, 0x00000000));
};
```

**v4-blackhole.conf:**
```
# Time: 2026-03-12T14:30:00Z
# Source: 203.0.113.10
# Gbps: 8.5 (exceeded emergency threshold)

route 203.0.113.10/32 blackhole {
  bgp_community.add((65535, 666));
};
```

---

## Configuration Reference

### Complete Configuration File

```yaml
# config.yaml - Production Configuration

service:
  name: "ddos-guard"
  log_level: "info"
  dry_run: false              # Set to true for testing (no BIRD reloads)

# ClickHouse Connection
clickhouse:
  host: "clickhouse.akvorado.example.com"
  port: 9000
  database: "default"
  user: "ddos_guard"
  password: "${CLICKHOUSE_PASSWORD}"  # Environment variable
  timeout: 30

# Detection Parameters
detection:
  interval_seconds: 60
  max_rules: 20              # Maximum concurrent mitigation rules
  query_minutes: 60          # Query last N minutes of data

  thresholds:
    gbps: 1.0                # General threshold
    udp_gbps: 0.2            # UDP-specific threshold
    gbps_with_sources: 0.1   # Threshold with many sources
    min_sources: 20          # Minimum unique source IPs
    gbps_with_countries: 0.1 # Threshold with geographic dispersion
    min_countries: 10        # Minimum source countries

  # Emergency blackhole threshold
  emergency_threshold_gbps: 5.0

# BIRD Configuration
bird:
  config_dir: "/etc/bird/ddos"
  birdc_path: "/usr/sbin/birdc"
  base_config: "/etc/bird/bird.conf"

  # Communities
  blackhole_community: "65535:666"
  flowspec_rate_limit: "0x80060000 0x00000000"  # 0 bps = drop

# Alerting
alerting:
  enabled: true
  webhook_url: "https://hooks.example.com/ddos-alerts"
  timeout: 10

  # Alert on events
  on_detection: true
  on_mitigation: true
  on_error: true

  # Rate limiting (per target)
  alert_cooldown_seconds: 300

# Monitoring
monitoring:
  enabled: true
  metrics_file: "/var/log/ddos-guard/metrics.json"
  log_file: "/var/log/ddos-guard/detector.log"
```

---

## Implementation Roadmap

### Phase 1: Foundation (Day 1)

**Tasks:**
- [ ] Deploy ClickHouse materialized view schema
- [ ] Create project directory structure on BIRD server
- [ ] Install Python dependencies
- [ ] Create configuration file
- [ ] Test ClickHouse connectivity

**Deliverables:**
- ClickHouse schema deployed
- Python environment ready
- Config validated

### Phase 2: Detection Script (Day 1-2)

**Tasks:**
- [ ] Implement ClickHouse query function
- [ ] Implement detection threshold logic
- [ ] Create BIRD config generation functions
- [ ] Add config comparison (avoid unnecessary reloads)
- [ ] Implement BIRD reload via birdc
- [ ] Add logging

**Deliverables:**
- Detection script functional
- BIRD configs generated correctly
- Reload logic working

### Phase 3: Alerting & Safety (Day 2)

**Tasks:**
- [ ] Implement webhook alerting
- [ ] Add dry-run mode for testing
- [ ] Implement rule limits and cleanup
- [ ] Add health check endpoint
- [ ] Create systemd service

**Deliverables:**
- Alerting working
- Safety features in place
- Service management ready

### Phase 4: Testing & Tuning (Day 2-3)

**Tasks:**
- [ ] Run in dry-run mode for 24 hours
- [ ] Analyze detection results
- [ ] Tune thresholds based on normal traffic
- [ ] Test manual BIRD config reload
- [ ] Verify Flowspec propagation to VPP

**Deliverables:**
- Thresholds tuned
- No false positives
- BIRD integration verified

### Phase 5: Production Deployment (Day 3)

**Tasks:**
- [ ] Disable dry-run mode
- [ ] Enable systemd service
- [ ] Monitor for first week
- [ ] Document operational procedures
- [ ] Create runbook

**Deliverables:**
- System in production
- Team trained
- Documentation complete

---

## Project Structure

```
/opt/ddos-guard/
├── ddos_detector.py          # Main detection script
├── config.yaml               # Configuration file
├── requirements.txt          # Python dependencies
├── lib/
│   ├── __init__.py
│   ├── clickhouse_client.py  # ClickHouse interface
│   ├── bird_config.py        # BIRD config generation
│   ├── detector.py           # Detection logic
│   └── webhook.py            # Alerting
├── systemd/
│   └── ddos-guard.service    # Systemd service file
└── log/
    └── .gitkeep              # Log directory

/etc/bird/ddos/               # Generated configs (managed by script)
├── v4-flowspec.conf
├── v6-flowspec.conf
├── v4-blackhole.conf
└── v6-blackhole.conf
```

---

## Key Design Decisions

### 1. Use Existing Infrastructure

**Decision:** Leverage Akvorado + ClickHouse instead of building new collectors

**Rationale:**
- Already deployed and collecting flows
- Proven at scale
- No additional infrastructure needed
- Faster time to deployment

### 2. Python Over Go

**Decision:** Use Python instead of Go for detection script

**Rationale:**
- Simpler implementation
- Excellent ClickHouse driver support
- Easier to maintain and modify
- Performance adequate for 60-second polling

### 3. File-Based BIRD Configuration

**Decision:** Generate static config files instead of using BIRD control socket

**Rationale:**
- Simpler and more reliable
- Config files serve as audit trail
- Easy to review changes before reload
- Aligns with maintainer's workflow (statics.yaml approach)

### 4. Dual Mitigation Strategy

**Decision:** Support both Flowspec and RTBH

**Rationale:**
- Flowspec for surgical filtering (preserves service)
- RTBH for emergency situations (protects infrastructure)
- Provides graduated response

### 5. Pre-aggregated Materialized Views

**Decision:** Use ClickHouse materialized views for detection

**Rationale:**
- Reduces query complexity
- Improves query performance
- Automatic data lifecycle (TTL)
- Real-time aggregation

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| False positives | High | Medium | Start with dry-run mode, tune thresholds gradually |
| ClickHouse overload | Medium | Low | Use materialized views, limit query frequency |
| BIRD config errors | High | Low | Validate configs before reload, test in staging |
| Alert fatigue | Medium | Medium | Alert deduplication, cooldown periods |
| Flowspec not supported | High | Low | Fallback to RTBH only, verify router support |

---

## Success Criteria

### Functional Requirements
- [ ] Detect attacks within 60 seconds
- [ ] Support both Flowspec and RTBH mitigation
- [ ] Maximum 20 concurrent rules
- [ ] Automatic rule expiration (6 hours)
- [ ] Webhook alerts within 5 seconds

### Non-Functional Requirements
- [ ] < 1% false positive rate (after tuning)
- [ ] Zero BIRD configuration errors
- [ ] Alert delivery 99.9% reliable
- [ ] Script uptime 99.9%

### Operational Requirements
- [ ] Complete runbook documentation
- [ ] Dry-run mode for testing
- [ ] Health check endpoint
- [ ] Team training completed

---

## Appendix A: Webhook Payload Format

### Detection Alert

```json
{
  "event": "ddos_detected",
  "timestamp": "2026-03-12T14:30:00Z",
  "severity": "high",
  "target": {
    "ip": "203.0.113.10",
    "protocol": "UDP",
    "port": 53
  },
  "metrics": {
    "gbps": 1.234,
    "mpps": 0.456,
    "sources": 45,
    "countries": 12
  },
  "mitigation": {
    "type": "flowspec",
    "rule_count": 1
  }
}
```

### Mitigation Applied Alert

```json
{
  "event": "mitigation_applied",
  "timestamp": "2026-03-12T14:30:01Z",
  "target": {
    "ip": "203.0.113.10"
  },
  "rules": [
    {
      "type": "flowspec",
      "config_file": "/etc/bird/ddos/v4-flowspec.conf"
    }
  ],
  "bird_reloaded": true
}
```

---

## Appendix B: VPP Router Configuration

### Flowspec Configuration

```
vrf public
 address-family ipv4 flowspec
 address-family ipv6 flowspec
!
router bgp 12322
 address-family vpnv4 flowspec
 address-family vpnv6 flowspec
 neighbor-group FLOWSPEC_IPV4_PUBLIC
  remote-as 64666
  ebgp-multihop 255
  update-source Loopback10
  address-family ipv4 flowspec
   long-lived-graceful-restart stale-time send 86400 accept 86400
   route-policy accept in
   route-policy drop out
   maximum-prefix 100 90
   validation disable
  !
  address-family ipv6 flowspec
   long-lived-graceful-restart stale-time send 86400 accept 86400
   route-policy accept in
   route-policy drop out
   maximum-prefix 100 90
   validation disable
  !
 !
 vrf public
  address-family ipv4 flowspec
  address-family ipv6 flowspec
  neighbor 192.0.2.1
   use neighbor-group FLOWSPEC_IPV4_PUBLIC
   description ddos-guard
```

### Enable Flowspec on Interfaces

```
flowspec
 vrf public
  address-family ipv4
   local-install interface-all
  !
  address-family ipv6
   local-install interface-all
  !
 !
!
```

### RTBH Configuration

```
router static
 vrf public
  address-family ipv4 unicast
   192.0.2.1/32 Null0 description "BGP blackhole"
  !
!
route-policy blackhole_ipv4_in_public
  if destination in (0.0.0.0/0 le 31) then
    drop
  endif
  set next-hop 192.0.2.1
  done
end-policy
```

---

## Appendix C: Operational Procedures

### Check Current Status

```bash
# View active mitigations
birdc show route table flowtab4
birdc show route table ddos_blackhole

# Check script logs
tail -f /var/log/ddos-guard/detector.log

# View ClickHouse detection data
clickhouse-client --query "SELECT * FROM ddos_logs WHERE TimeReceived > now() - INTERVAL 10 MINUTE"
```

### Manual Rule Removal

```bash
# Remove specific target from BIRD configs
sudo vi /etc/bird/ddos/v4-flowspec.conf
sudo birdc configure
```

### Emergency Stop

```bash
# Stop the service
sudo systemctl stop ddos-guard

# Clear all DDoS rules
sudo truncate -s 0 /etc/bird/ddos/*.conf
sudo birdc configure
```

### Testing in Dry-Run Mode

```bash
# Edit config
sudo vi /opt/ddos-guard/config.yaml
# Set dry_run: true

# Restart service
sudo systemctl restart ddos-guard

# Monitor what would be done
sudo tail -f /var/log/ddos-guard/detector.log
```

---

## Appendix D: Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CLICKHOUSE_PASSWORD` | Yes | ClickHouse authentication password |
| `WEBHOOK_SECRET` | No | Secret for webhook HMAC signature |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-12 | Initial | Created simplified plan based on Akvorado approach |

---

## Next Steps

1. **Review this document** with network team
2. **Verify ClickHouse schema** compatibility with existing Akvorado setup
3. **Confirm BIRD configuration** on VPP routers supports Flowspec
4. **Begin Phase 1** implementation (ClickHouse schema deployment)
5. **Schedule deployment window** for production

---

**Document Status:** Planning Complete

**Ready for Implementation:** Yes

**Estimated Timeline:** 3 days

**Last Updated:** 2026-03-12
