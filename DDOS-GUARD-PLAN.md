# DDoS-Guard: Technical Implementation Plan

## Executive Summary

Custom Go-based DDoS detection and mitigation system for high-performance network infrastructure (VPP + BIRD 2.0).

**Infrastructure:**
- 10 Gbps capacity
- Own ASN with IXP and Transit connections
- VPP + BIRD 2.0 stack
- Software-only solution
- 30-day metrics retention

**Key Features:**
- Real-time flow analysis via Kafka
- Threshold-based detection (pps/bps)
- Multi-tier mitigation (RTBH, Flowspec, VPP ACL)
- Slack/IRC alerting
- Sub-second to seconds detection latency

---

## System Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │ VPP (sFlow)  │  │ Edge Router  │  │    IXP       │                       │
│  │   Export     │  │   sFlow      │  │   Port       │                       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                       │
└─────────┼─────────────────┼─────────────────┼────────────────────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INGESTION LAYER                                  │
│                          GoFlow Collector                                   │
│                    (sFlow → Kafka Topic: "flows")                           │
└─────────────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DDOS-GUARD SERVICE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │  Collector  │───▶│   Engine    │───▶│  Mitigator  │                     │
│  │   (Kafka)   │    │(Thresholds) │    │(BIRD/VPP)   │                     │
│  └─────────────┘    └──────┬──────┘    └─────────────┘                     │
│                            │                                               │
│                            ▼                                               │
│                   ┌─────────────────┐                                       │
│                   │ Event Channels  │                                       │
│                   │  • Detection    │                                       │
│                   │  • Mitigation   │                                       │
│                   │  • Alert        │                                       │
│                   └────────┬────────┘                                       │
│                            │                                               │
│              ┌─────────────┼─────────────┐                                 │
│              ▼             ▼             ▼                                 │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                     │
│  │    Slack      │ │     IRC       │ │   InfluxDB    │                     │
│  │   Webhook     │ │     Bot       │ │  (Metrics)    │                     │
│  └───────────────┘ └───────────────┘ └───────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction

```
┌────────────────────────────────────────────────────────────────────┐
│                      PER-FLOW PROCESSING                           │
│                                                                    │
│  Kafka Message                                                     │
│       │                                                            │
│       ▼                                                            │
│  ┌─────────────┐                                                   │
│  │  Collector  │ ──▶ Spawn goroutine per flow                      │
│  │   Worker    │                                                   │
│  └──────┬──────┘                                                   │
│         │                                                          │
│         ▼                                                          │
│  ┌─────────────┐     ┌─────────────┐                               │
│  │    Flow     │────▶│    Window   │                               │
│  │   Record    │     │   Manager   │                               │
│  └─────────────┘     └──────┬──────┘                               │
│                             │                                      │
│                             ▼                                      │
│                     ┌───────────────┐                              │
│                     │ Check Threshold│                             │
│                     │  pps/bps > X?  │                             │
│                     └───────┬───────┘                              │
│                             │                                      │
│              ┌──────────────┴──────────────┐                       │
│              │                             │                       │
│              ▼                             ▼                       │
│        ┌──────────┐                ┌──────────┐                   │
│        │  Normal  │                │  Attack  │                   │
│        │  (exit)  │                │  Detected                   │
│        └──────────┘                └────┬─────┘                   │
│                                         │                         │
│                                         ▼                         │
│                              ┌─────────────────┐                  │
│                              │   Mitigation    │                  │
│                              │   Controller    │                  │
│                              └────────┬────────┘                  │
│                                       │                           │
│              ┌────────────────────────┼────────────────────┐      │
│              ▼                        ▼                    ▼      │
│       ┌─────────────┐        ┌─────────────┐      ┌────────────┐ │
│       │  BIRD RTBH  │        │BIRD Flowspec│      │ VPP ACL    │ │
│       │  (Socket)   │        │   (BGP)     │      │ (Binary)   │ │
│       └─────────────┘        └─────────────┘      └────────────┘ │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Core Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | Go | 1.21+ | Service implementation |
| Message Queue | Apache Kafka | 3.x | Flow data ingestion |
| Time-Series DB | InfluxDB | 2.x | Metrics storage |
| Visualization | Grafana | Latest | Dashboards |
| Routing Daemon | BIRD | 2.0+ | RTBH and Flowspec |
| Data Plane | VPP | Latest | High-performance forwarding |

### Go Dependencies

```go
// Core
require (
    github.com/Shopify/sarama v1.40.0        // Kafka client
    github.com/influxdata/influxdb-client-go/v2 v2.12.0  // InfluxDB
    gopkg.in/yaml.v3 v3.0.1                  // Config parsing
    github.com/sirupsen/logrus v1.9.0        // Structured logging
)

// Optional (for Flowspec)
require (
    github.com/osrg/gobgp/v3 v3.0.0          // BGP/Flowspec support
    git.fd.io/govpp.git v0.7.0               // VPP binary API
)

// Testing
require (
    github.com/stretchr/testify v1.8.0       // Unit testing
    github.com/IBM/sarama v1.40.0            // Kafka testing
)
```

---

## Data Models

### Flow Record (Input)

```go
type FlowRecord struct {
    // Identification
    SrcIP       net.IP    `json:"src_ip"`
    DstIP       net.IP    `json:"dst_ip"`
    SrcPort     uint16    `json:"src_port"`
    DstPort     uint16    `json:"dst_port"`
    Protocol    uint8     `json:"protocol"`     // 6=TCP, 17=UDP, 1=ICMP
    
    // Metrics
    Packets     uint64    `json:"packets"`
    Bytes       uint64    `json:"bytes"`
    SampleRate  uint32    `json:"sample_rate"`  // Sampling rate (e.g., 1000 = 1:1000)
    
    // Timing
    Timestamp   time.Time `json:"timestamp"`
    Duration    uint32    `json:"duration_ms"`
    
    // Additional
    TCPFlags    uint8     `json:"tcp_flags,omitempty"`
    TOS         uint8     `json:"tos,omitempty"`
}
```

### Traffic Window (Internal)

```go
type TrafficWindow struct {
    // Identification
    DstIP       net.IP    
    
    // Time bounds
    StartTime   time.Time
    EndTime     time.Time
    
    // Aggregated metrics (extrapolated from sample rate)
    TotalPackets    uint64    // Packets * SampleRate
    TotalBytes      uint64    // Bytes * SampleRate
    FlowCount       uint32
    UniqueSrcIPs    map[string]struct{}
    
    // Rates (calculated on demand)
    PacketsPerSec   float64
    BytesPerSec     float64
    
    // State
    IsMitigating    bool
    MitigationStart time.Time
}

// WindowManager manages all sliding windows
type WindowManager struct {
    windows     map[string]*TrafficWindow  // key: dst_ip
    mutex       sync.RWMutex
    config      WindowConfig
    eventChan   chan DetectionEvent
}
```

### Detection Event

```go
type DetectionEvent struct {
    ID            string
    Timestamp     time.Time
    Type          string           // "threshold_exceeded", "pattern_detected"
    Severity      string           // "low", "medium", "high", "critical"
    
    // Target
    DstIP         net.IP
    DstPort       uint16
    Protocol      uint8
    
    // Metrics
    PeakPPS       uint64
    PeakBPS       uint64
    Duration      time.Duration
    UniqueSrcIPs  int
    
    // Detection details
    ThresholdName string
    ThresholdValue uint64
    ActualValue   uint64
    
    // Context
    GeoInfo       GeoLocation
    ASNInfo       ASNDetails
}
```

### Mitigation Rule (Ephemeral)

```go
type MitigationRule struct {
    ID            string
    Type          string           // "bird_rtbh", "bird_flowspec", "vpp_acl"
    
    // Target
    TargetIP      net.IP
    TargetPrefix  int              // CIDR prefix (e.g., 32 for single IP)
    TargetPort    uint16           // 0 = all ports
    Protocol      uint8            // 0 = all protocols
    
    // Action
    Action        string           // "drop", "rate-limit", "redirect"
    RateLimit     uint64           // For rate-limit action (bps)
    
    // Lifecycle
    CreatedAt     time.Time
    ExpiresAt     time.Time        // Auto-expiry
    Duration      time.Duration
    
    // Metadata
    Reason        string
    DetectionID   string           // Reference to triggering event
    Confidence    float64          // 0.0 - 1.0
    
    // State
    IsActive      bool
    AppliedAt     *time.Time
    RemovedAt     *time.Time
    
    // Effectiveness tracking
    Metrics       RuleMetrics
}

type RuleMetrics struct {
    PacketsBlocked    uint64
    BytesBlocked      uint64
    FalsePositives    int
}
```

---

## Detection Logic

### Threshold Configuration

```yaml
detection:
  # Primary thresholds
  thresholds:
    pps: 1000000              # 1 million packets/sec
    bps: 5368709120           # 5 Gbps
    flows_per_sec: 10000      # Flow setup rate
  
  # Sliding window configuration
  windows:
    burst:
      duration: 10s           # Short window for burst detection
      multiplier: 1.0         # Use full threshold
    sustained:
      duration: 60s           # Long window for sustained attacks
      multiplier: 0.5         # 50% of threshold (2.5 Gbps / 500k pps)
  
  # Cooldown and escalation
  cooldown_seconds: 300       # 5 minutes before auto-unblock
  escalation_delay: 60        # 60 seconds before escalating
  
  # Pattern detection
  patterns:
    syn_flood:
      enabled: true
      syn_ratio_threshold: 0.9   # >90% SYN packets
      min_pps: 100000
    
    amplification:
      enabled: true
      protocols: ["dns", "ntp", "ssdp", "memcached"]
      min_factor: 10              # 10x amplification factor
```

### Detection Algorithm

```
For each flow record:
    1. Calculate extrapolated metrics:
       - actual_packets = flow.Packets * flow.SampleRate
       - actual_bytes = flow.Bytes * flow.SampleRate
    
    2. Update sliding window for DstIP:
       - Add to existing window OR create new window
       - Recalculate window duration
       - Update aggregates
    
    3. Calculate rates:
       - pps = TotalPackets / window_duration
       - bps = TotalBytes / window_duration
    
    4. Check thresholds:
       - IF pps > threshold_pps: trigger_detection("pps_exceeded")
       - IF bps > threshold_bps: trigger_detection("bps_exceeded")
    
    5. Check patterns (optional):
       - IF syn_ratio > 0.9: trigger_detection("syn_flood")
       - IF amplification_detected: trigger_detection("amplification")
    
    6. Emit DetectionEvent to channel
```

### Escalation Logic

```go
func (e *Engine) determineMitigation(event DetectionEvent) MitigationDecision {
    switch {
    // Critical: Immediate RTBH
    case event.PeakBPS > 5*GBPS:
        return MitigationDecision{
            Method:   "bird_rtbh",
            Action:   "drop",
            Duration: 5 * time.Minute,
            Priority: 1,
        }
    
    // High: Flowspec rate-limit
    case event.PeakBPS > 2*GBPS:
        return MitigationDecision{
            Method:   "bird_flowspec",
            Action:   "rate-limit",
            Rate:     1 * GBPS,
            Duration: 10 * time.Minute,
            Priority: 2,
        }
    
    // Medium: VPP ACL
    case event.PeakPPS > 500000:
        return MitigationDecision{
            Method:   "vpp_acl",
            Action:   "drop",
            Duration: 15 * time.Minute,
            Priority: 3,
        }
    
    // Low: Monitor only
    default:
        return MitigationDecision{
            Method:   "none",
            Action:   "alert_only",
        }
    }
}
```

---

## Mitigation Modules

### 1. BIRD RTBH Controller

**Purpose:** Emergency traffic blackholing via BGP communities

**Implementation:**
```go
type BIRDController struct {
    socketPath string        // /var/run/bird/bird.ctl
    mutex      sync.Mutex
}

// Methods:
// - Connect() error
// - AddRTBH(ip net.IP, community string) error
// - RemoveRTBH(ip net.IP) error
// - ListActiveRTBH() ([]RTBHEntry, error)
// - ReloadConfig() error

// BIRD Configuration Template:
const birdRTBHConfig = `
ro table ddos_blackhole {
{{- range .Entries}}
  ro {{.Prefix}} blackhole community {{.Community}};
{{- end}}
}
`
```

**BIRD Integration:**
- Uses BIRD control socket for dynamic configuration
- Updates `ro table ddos_blackhole` route table
- Applies BGP community for upstream propagation
- Supports automatic config reload

### 2. BIRD Flowspec Controller

**Purpose:** Granular filtering via BGP Flowspec (RFC 5575)

**Implementation:**
```go
type FlowspecController struct {
    birdSocket string
    gobgpClient *gobgp.BgpServer  // Optional: Use GoBGP for Flowspec
}

// Methods:
// - AddFlowspecRule(rule FlowspecRule) error
// - RemoveFlowspecRule(id string) error
// - ListFlowspecRules() ([]FlowspecRule, error)

// Flowspec Actions:
// - Traffic-rate (rate-limit)
// - Traffic-action (drop, redirect)
// - Redirect (to specific next-hop)
// - Traffic-marking (DSCP)
```

**Flowspec Rules:**
```
Match criteria:
- Destination IP/prefix
- Source IP/prefix
- Protocol (TCP, UDP, ICMP)
- Port(s)
- Packet length
- Fragmentation

Actions:
- rate-limit <bits-per-second>
- discard
- redirect <next-hop>
```

### 3. VPP ACL Controller

**Purpose:** Fast, granular packet filtering at data plane

**Implementation:**
```go
type VPPController struct {
    apiSocket  string          // /run/vpp/api.sock
    isConnected bool
    // VPP API connection
}

// Methods:
// - Connect() error
// - AddACL(rule ACLRule) (uint32, error)  // Returns ACL index
// - DeleteACL(aclIndex uint32) error
// - ListACLs() ([]ACLRule, error)
// - ApplyACLToInterface(ifIndex uint32, aclIndex uint32, direction string) error

// VPP ACL Rule:
type ACLRule struct {
    SrcIP       net.IP
    SrcIPPrefix uint8      // CIDR prefix
    DstIP       net.IP
    DstIPPrefix uint8
    Protocol    uint8      // 0 = any
    SrcPort     uint16     // 0 = any
    DstPort     uint16     // 0 = any
    Action      uint8      // 0 = permit, 1 = deny
}
```

**VPP Integration:**
- Uses VPP binary API (via GoVPP library)
- Creates ACL tables with deny rules
- Applies ACLs to interfaces
- Supports per-interface ACLs
- Very fast: millions of packets/sec filtering capability

---

## Alerting System

### Slack Integration

```go
type SlackNotifier struct {
    webhookURL string
    channel    string
    client     *http.Client
}

// Alert Format:
type SlackMessage struct {
    Channel   string       `json:"channel"`
    Username  string       `json:"username"`
    IconEmoji string       `json:"icon_emoji"`
    Text      string       `json:"text"`
    Attachments []Attachment `json:"attachments"`
}

// Alert Triggers:
// - DetectionEvent (immediate)
// - MitigationApplied (confirmation)
// - MitigationExpired (auto-removal)
// - SystemError (operational issues)
```

**Example Alert:**
```json
{
  "channel": "#noc",
  "username": "DDoS-Guard",
  "icon_emoji": ":warning:",
  "text": "DDoS Attack Detected!",
  "attachments": [{
    "color": "danger",
    "fields": [
      {"title": "Target", "value": "203.0.113.10", "short": true},
      {"title": "Type", "value": "Volumetric", "short": true},
      {"title": "Peak Traffic", "value": "8.2 Gbps", "short": true},
      {"title": "Mitigation", "value": "RTBH Applied", "short": true}
    ]
  }]
}
```

### IRC Integration

```go
type IRCBot struct {
    server   string
    channels []string
    nickname string
    conn     net.Conn
}

// Features:
// - Connect to IRC server
// - Join channels
// - Send alerts
// - Command handling (e.g., !status, !list)
```

**IRC Commands:**
```
!status          - Show system status
!attacks         - List active attacks
!mitigations     - List active mitigations
!block <ip>      - Manual RTBH
!unblock <ip>    - Remove RTBH
!help            - Show commands
```

---

## Metrics & Monitoring

### InfluxDB Schema

```
Bucket: ddos-metrics
Retention: 30 days

Measurements:
--------------
1. traffic_stats
   - Fields: packets, bytes, flows, unique_src_ips
   - Tags: dst_ip, protocol, port
   - Time: per-second aggregation

2. detection_events
   - Fields: pps, bps, severity_score
   - Tags: event_type, dst_ip, mitigation_method
   - Time: event timestamp

3. mitigation_rules
   - Fields: duration_seconds, packets_blocked
   - Tags: rule_type, target_ip, action
   - Time: rule creation timestamp

4. system_health
   - Fields: kafka_lag, processing_latency_ms, goroutines
   - Tags: component
   - Time: continuous
```

### Grafana Dashboards

**Dashboard 1: Real-Time Overview**
- Current traffic (Gbps, Mpps)
- Active attacks (count)
- Active mitigations (count)
- Top attacked destinations
- Geographic attack map

**Dashboard 2: Attack Details**
- Attack timeline
- Traffic graphs (per target)
- Mitigation effectiveness
- False positive rate

**Dashboard 3: System Health**
- Kafka consumer lag
- Processing latency
- Goroutine count
- Memory usage
- Error rates

---

## Configuration Reference

### Complete Configuration File

```yaml
# config.yaml - Production Configuration

service:
  name: "ddos-guard"
  version: "1.0.0"
  log_level: "info"           # debug, info, warn, error
  log_format: "json"          # json, text

# Data Collection
collector:
  type: "kafka"
  kafka:
    brokers:
      - "kafka1.example.com:9092"
      - "kafka2.example.com:9092"
    topic: "flows"
    consumer_group: "ddos-guard"
    workers: 10                # Concurrent consumers
    session_timeout: "30s"
    heartbeat_interval: "3s"
  
  # Alternative: HTTP webhook
  # http:
  #   listen: ":8080"
  #   path: "/flows"

# Detection Engine
detection:
  # Thresholds
  thresholds:
    pps: 1000000               # 1M packets/sec
    bps: 5368709120            # 5 Gbps
    flows_per_sec: 10000
  
  # Sliding windows
  windows:
    burst:
      duration: "10s"
      multiplier: 1.0
    sustained:
      duration: "60s"
      multiplier: 0.5
  
  # Pattern detection
  patterns:
    syn_flood:
      enabled: true
      syn_ratio_threshold: 0.9
      min_pps: 100000
    amplification:
      enabled: true
      protocols: ["dns", "ntp", "ssdp"]
      min_factor: 10
  
  # Cooldown and lifecycle
  cooldown_seconds: 300        # Auto-unblock after 5 min
  max_mitigation_duration: 3600 # Max 1 hour
  
  # Rate limiting
  max_mitigations_per_minute: 10

# Mitigation Controller
mitigation:
  # Priority order: first match wins
  methods:
    - name: "bird_rtbh"
      enabled: true
      priority: 1
      config:
        socket: "/var/run/bird/bird.ctl"
        community: "64512:666"
        upstream_community: "64512:999"
        max_rules: 1000
        apply_when:
          bps_greater_than: 5368709120  # 5 Gbps
      
    - name: "bird_flowspec"
      enabled: true
      priority: 2
      config:
        socket: "/var/run/bird/bird.ctl"
        local_as: 64512
        apply_when:
          bps_greater_than: 2147483648  # 2 Gbps
        actions:
          - type: "rate-limit"
            rate: 1073741824              # 1 Gbps
      
    - name: "vpp_acl"
      enabled: true
      priority: 3
      config:
        api_socket: "/run/vpp/api.sock"
        table_id: 0
        apply_when:
          pps_greater_than: 500000
        interfaces: ["TenGigabitEthernet1/0/0"]

# Alerting
alerting:
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"  # Environment variable
    channel: "#noc-alerts"
    username: "DDoS-Guard"
    icon_emoji: ":warning:"
    min_severity: "medium"       # low, medium, high, critical
  
  irc:
    enabled: true
    server: "irc.example.com:6667"
    nickname: "ddos-guard"
    channels:
      - "#noc"
      - "#operations"
    ssl: false
    password: "${IRC_PASSWORD}"

# Metrics Export
metrics:
  enabled: true
  interval: "10s"
  
  influxdb:
    url: "http://influxdb.example.com:8086"
    token: "${INFLUX_TOKEN}"
    org: "noc"
    bucket: "ddos-metrics"
    batch_size: 100
    flush_interval: "5s"

# Advanced Settings
advanced:
  # Concurrency
  worker_pool_size: 100
  channel_buffer_size: 10000
  
  # Memory
  max_windows: 100000          # Max concurrent IP tracking
  window_cleanup_interval: "60s"
  
  # Performance
  sample_rate_extrapolation: true
  enable_profiling: false
  pprof_port: 6060
  
  # Reliability
  circuit_breaker_threshold: 5
  circuit_breaker_timeout: "30s"
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)

**Goals:** Core framework, configuration, basic flow ingestion

**Tasks:**
- [ ] Initialize Go module and project structure
- [ ] Implement configuration loader (YAML)
- [ ] Create data models (FlowRecord, TrafficWindow, etc.)
- [ ] Build Kafka consumer with goroutine-per-message
- [ ] Implement sliding window manager
- [ ] Add basic logging (Logrus)
- [ ] Create unit tests for core components
- [ ] Docker Compose for local testing

**Deliverables:**
- Working flow ingestion
- Window aggregation functional
- Configuration validated

### Phase 2: Detection Engine (Week 2)

**Goals:** Threshold detection, pattern matching

**Tasks:**
- [ ] Implement threshold checking logic
- [ ] Add pps/bps calculation
- [ ] Build event channel system
- [ ] Create DetectionEvent pipeline
- [ ] Add pattern detection (SYN flood)
- [ ] Implement escalation logic
- [ ] Add GeoIP enrichment
- [ ] Build alerting framework (interfaces)

**Deliverables:**
- Detection events generated
- Threshold logic tested
- Event pipeline working

### Phase 3: Mitigation Controllers (Week 3)

**Goals:** BIRD RTBH, VPP ACL integration

**Tasks:**
- [ ] BIRD control socket integration
- [ ] RTBH add/remove logic
- [ ] VPP binary API connection
- [ ] VPP ACL CRUD operations
- [ ] Mitigation rule lifecycle (expiry)
- [ ] Rule prioritization
- [ ] Error handling and rollback
- [ ] Integration tests with BIRD/VPP

**Deliverables:**
- Mitigation rules applied
- Auto-expiry working
- Both BIRD and VPP functional

### Phase 4: Alerting & UI (Week 4)

**Goals:** Slack, IRC, Grafana dashboards

**Tasks:**
- [ ] Slack webhook integration
- [ ] IRC bot implementation
- [ ] Rich alert formatting
- [ ] IRC command handlers
- [ ] InfluxDB metrics export
- [ ] Grafana dashboard creation
- [ ] Alert routing logic
- [ ] Documentation

**Deliverables:**
- Notifications sent
- Dashboards visible
- IRC bot responding

### Phase 5: Testing & Hardening (Week 5)

**Goals:** Load testing, edge cases, production readiness

**Tasks:**
- [ ] Load test with simulated 10Gbps flows
- [ ] Kafka partition testing
- [ ] Memory profiling and optimization
- [ ] Circuit breaker implementation
- [ ] Graceful shutdown handling
- [ ] Configuration hot-reload
- [ ] Health check endpoints
- [ ] Runbook documentation

**Deliverables:**
- Performance validated
- Production-ready code
- Documentation complete

### Phase 6: Production Deployment (Week 6)

**Goals:** Deploy to production, monitoring-only mode

**Tasks:**
- [ ] Production configuration
- [ ] Deploy to staging environment
- [ ] Monitor for 1 week (detection only)
- [ ] Tune thresholds based on real traffic
- [ ] Gradually enable mitigation
- [ ] 24/7 on-call rotation
- [ ] Post-deployment review

**Deliverables:**
- System in production
- Team trained
- Operational procedures established

---

## Project Structure

```
ddos-guard/
├── cmd/
│   └── ddos-guard/
│       └── main.go                 # Entry point
│
├── internal/
│   ├── collector/
│   │   ├── kafka.go               # Kafka consumer
│   │   ├── http.go                # HTTP webhook (optional)
│   │   └── collector.go           # Interface definitions
│   │
│   ├── engine/
│   │   ├── window.go              # Sliding window implementation
│   │   ├── detector.go            # Threshold detection
│   │   ├── patterns.go            # Pattern matching (SYN flood, etc.)
│   │   └── engine.go              # Main detection engine
│   │
│   ├── mitigator/
│   │   ├── bird_rtbh.go           # BIRD RTBH controller
│   │   ├── bird_flowspec.go       # BIRD Flowspec controller
│   │   ├── vpp_acl.go             # VPP ACL controller
│   │   ├── manager.go             # Mitigation rule manager
│   │   └── interfaces.go          # Controller interfaces
│   │
│   ├── notifier/
│   │   ├── slack.go               # Slack webhook
│   │   ├── irc.go                 # IRC bot
│   │   └── interfaces.go          # Notifier interface
│   │
│   └── metrics/
│       ├── influxdb.go            # InfluxDB client
│       └── interfaces.go          # Metrics interface
│
├── pkg/
│   ├── config/
│   │   ├── config.go              # Configuration structs
│   │   └── loader.go              # YAML loader
│   │
│   └── models/
│       ├── flow.go                # Flow record models
│       ├── window.go              # Window models
│       ├── events.go              # Detection events
│       └── rules.go               # Mitigation rules
│
├── deployments/
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   │
│   ├── kubernetes/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   │
│   └── systemd/
│       └── ddos-guard.service
│
├── dashboards/
│   └── grafana/
│       ├── overview.json
│       ├── attacks.json
│       └── system.json
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS.md
│   └── API.md
│
├── config/
│   └── config.example.yaml
│
├── scripts/
│   ├── build.sh
│   ├── test.sh
│   └── deploy.sh
│
├── test/
│   ├── unit/
│   ├── integration/
│   └── load/
│
├── go.mod
├── go.sum
├── Makefile
├── README.md
└── LICENSE
```

---

## Key Design Decisions

### 1. Per-Flow Goroutines

**Decision:** Use goroutine-per-flow processing

**Rationale:**
- Natural fit for Go concurrency model
- Isolated processing per flow
- Easy to reason about
- Scales well with Go scheduler

**Trade-offs:**
- Higher memory usage (but acceptable for 10Gbps)
- Need careful resource limits

### 2. Kafka Over HTTP

**Decision:** Use Kafka for flow ingestion

**Rationale:**
- Decouples GoFlow from detection service
- Provides backpressure handling
- Supports multiple consumers
- Persistent queue for reliability

**Trade-offs:**
- Additional infrastructure (Kafka cluster)
- Slightly higher latency (acceptable for seconds-level detection)

### 3. Ephemeral Mitigation Rules

**Decision:** Mitigation rules are temporary (no persistence)

**Rationale:**
- Simplifies implementation
- Reduces state management complexity
- Auto-cleanup prevents stale rules
- Consistent with "always verify" approach

**Trade-offs:**
- Rules lost on service restart
- Need external audit trail (InfluxDB)

### 4. Multiple Mitigation Methods

**Decision:** Support RTBH, Flowspec, and VPP ACL

**Rationale:**
- Provides graduated response
- RTBH for emergencies (fastest)
- Flowspec for selective filtering
- VPP ACL for granular control

**Priority:**
1. RTBH (drop all traffic to victim)
2. Flowspec (rate-limit or filter)
3. VPP ACL (fine-grained rules)

### 5. Code-Based Logic Over Configuration

**Decision:** Use Go code for detection logic (not DSL)

**Rationale:**
- Full power of Go language
- Type safety
- Easy to test
- Version controlled

**Trade-offs:**
- Requires recompile for logic changes
- (Mitigation: Hot-reload or config-driven thresholds)

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| False positives | High | Medium | Gradual rollout, monitoring mode, quick rollback |
| Performance at 10Gbps | High | Low | Load testing, horizontal scaling, optimization |
| BIRD/VPP connectivity | High | Low | Health checks, circuit breakers, alerts |
| Kafka lag | Medium | Medium | Monitoring, consumer scaling, backpressure |
| Memory exhaustion | Medium | Low | Window limits, GC tuning, resource quotas |
| Alert fatigue | Medium | Medium | Severity filtering, deduplication, cooldown periods |

---

## Success Criteria

### Functional Requirements
- [ ] Detect attacks at 1M pps and 5 Gbps thresholds
- [ ] Apply RTBH within 5 seconds of detection
- [ ] Support all three mitigation methods
- [ ] Send Slack/IRC alerts within 2 seconds
- [ ] Auto-expire rules after cooldown period
- [ ] Handle 10 Gbps sustained traffic

### Non-Functional Requirements
- [ ] < 1 second detection latency (after window fill)
- [ ] < 5 seconds mitigation latency
- [ ] 99.9% uptime
- [ ] < 1% false positive rate (after tuning)
- [ ] 30-day metrics retention
- [ ] Horizontal scaling capability

### Operational Requirements
- [ ] Complete runbook documentation
- [ ] Automated deployment pipeline
- [ ] 24/7 monitoring and alerting
- [ ] Team training completed
- [ ] Disaster recovery procedures

---

## Appendix A: GoFlow Configuration

### GoFlow Setup

```go
// goflow-config.yml
producer:
  type: "kafka"
  kafka:
    brokers:
      - "localhost:9092"
    topic: "flows"
    compression: "snappy"
    partition: "hash"           # Hash by flow key for locality

sflow:
  listen: ":6343"             # Standard sFlow port
  workers: 10
  sample-rate: 1000           # 1:1000 sampling

decode:
  version: "sflow-v5"
  fields:
    - "src_ip"
    - "dst_ip"
    - "src_port"
    - "dst_port"
    - "protocol"
    - "packets"
    - "bytes"
    - "tcp_flags"

format:
  type: "json"
  pretty: false
```

### VPP sFlow Configuration

```bash
# VPP CLI commands
set sflow enable
set sflow rate 1000                    # 1:1000 sampling
set sflow collector 192.168.1.10 6343  # GoFlow collector IP
set sflow interface TenGigabitEthernet1/0/0
```

---

## Appendix B: BIRD Configuration

### BIRD 2.0 Base Config

```
# bird.conf
log syslog all;
debug protocols all;

# Router ID
router id 192.168.1.1;

# Protocols
protocol device {
    scan time 10;
}

protocol direct {
    ipv4;
    ipv6;
}

protocol kernel {
    ipv4 {
        export all;
    };
}

protocol kernel {
    ipv6 {
        export all;
    };
}

# Static routes (example)
protocol static {
    ipv4;
}

# Upstream BGP sessions
protocol bgp upstream1 {
    description "Upstream Provider 1";
    local as 64512;
    neighbor 192.0.2.1 as 64513;
    
    ipv4 {
        import all;
        export filter {
            # Accept all, but could filter here
            accept;
        };
    };
}

# DDoS Blackhole route table
ro table ddos_blackhole;

# Function to check if prefix is in blackhole table
function is_blackholed() {
    return (roa_check(ddos_blackhole, net, bgp_path.last) != 0);
}

# Export filter for upstream
filter upstream_out {
    if is_blackholed() then {
        bgp_community.add((64512, 666));  # Blackhole community
        accept;
    }
    accept;
}

# Control socket for API
protocol bgp {
    # ... upstream config ...
}
```

### RTBH Configuration

```
# Add to bird.conf
protocol static ddos_routes {
    ro table ddos_blackhole;
    
    # These routes will be dynamically added/removed
    # by the DDoS-Guard service via control socket
}
```

---

## Appendix C: VPP Configuration

### VPP Startup Config

```bash
# /etc/vpp/startup.conf
unix {
  nodaemon
  log /var/log/vpp/vpp.log
  full-coredump
  cli-listen /run/vpp/cli.sock
  gid vpp
}

api-trace {
  on
}

api-segment {
  gid vpp
}

socksvr {
  default
}

cpu {
  main-core 0
  corelist-workers 1-3
}

dpdk {
  dev 0000:01:00.0
  dev 0000:01:00.1
  num-mbufs 65536
}

plugins {
  plugin sflow_plugin.so { enable }
  plugin acl_plugin.so { enable }
}
```

### VPP ACL Setup

```bash
# VPP CLI
# Create ACL table
acl add deny src 192.0.2.1/32, permit

# Apply to interface
set interface acl input TenGigabitEthernet1/0/0 acl 0

# Show ACLs
show acl
```

---

## Appendix D: Environment Setup

### Development Environment

```bash
# Prerequisites
go version  # >= 1.21

# Clone and build
git clone <repo>
cd ddos-guard
go mod download
go build ./cmd/ddos-guard

# Run tests
go test ./...

# Run locally
./ddos-guard -config config.yaml
```

### Docker Compose (Testing)

```yaml
# docker-compose.yml
version: '3.8'

services:
  ddos-guard:
    build: .
    volumes:
      - ./config.yaml:/etc/ddos-guard/config.yaml
      - /var/run/bird:/var/run/bird:ro
      - /run/vpp:/run/vpp:ro
    environment:
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - INFLUX_TOKEN=${INFLUX_TOKEN}
    depends_on:
      - kafka
      - influxdb
    networks:
      - ddos-net

  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    depends_on:
      - zookeeper
    networks:
      - ddos-net

  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    networks:
      - ddos-net

  influxdb:
    image: influxdb:2.7
    environment:
      - INFLUXDB_DB=ddos-metrics
      - INFLUXDB_ADMIN_USER=admin
      - INFLUXDB_ADMIN_PASSWORD=${INFLUX_ADMIN_PASSWORD}
    volumes:
      - influxdb-data:/var/lib/influxdb2
    networks:
      - ddos-net

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./dashboards:/etc/grafana/provisioning/dashboards
      - grafana-data:/var/lib/grafana
    depends_on:
      - influxdb
    networks:
      - ddos-net

volumes:
  influxdb-data:
  grafana-data:

networks:
  ddos-net:
    driver: bridge
```

---

## Appendix E: API Reference

### Internal APIs

#### Detection Event

```go
// Subscribe to detection events
events := make(chan DetectionEvent, 100)
engine.Subscribe(events)

// Event structure
type DetectionEvent struct {
    ID          string
    Timestamp   time.Time
    Type        string           // "threshold_exceeded", "pattern_detected"
    Severity    string           // "low", "medium", "high", "critical"
    DstIP       net.IP
    PeakPPS     uint64
    PeakBPS     uint64
    // ... (see Data Models)
}
```

#### Mitigation Controller

```go
// Apply mitigation
rule := MitigationRule{
    Type:      "bird_rtbh",
    TargetIP:  net.ParseIP("203.0.113.10"),
    Action:    "drop",
    Duration:  5 * time.Minute,
}
id, err := mitigator.Apply(rule)

// Remove mitigation
err := mitigator.Remove(id)

// List active rules
rules, err := mitigator.ListActive()
```

#### Metrics

```go
// Record traffic
type TrafficPoint struct {
    Timestamp time.Time
    DstIP     net.IP
    Packets   uint64
    Bytes     uint64
}
metrics.RecordTraffic(point)

// Record detection
metrics.RecordDetection(event)

// Record mitigation
metrics.RecordMitigation(rule)
```

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-12 | Initial | Created initial technical specification |

---

## Next Steps

1. **Review this document** with stakeholders
2. **Finalize decisions** on any open questions
3. **Set up development environment** (Docker Compose)
4. **Begin Phase 1** implementation (Foundation)
5. **Schedule weekly reviews** to track progress

---

**Document Status:** Planning Complete

**Ready for Implementation:** Yes

**Last Updated:** 2026-03-12
