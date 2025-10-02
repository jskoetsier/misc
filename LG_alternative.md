# Looking Glass Alternatives for BIRD - AS 199036

## Overview
Since you're migrating from OpenBGPD to BIRD, you'll need to replace `bgplgd` with a BIRD-compatible looking glass solution. Here are the best modern alternatives for your AS 199036 NLNOG Ring setup.

## Recommended Alternatives

### 1. **Alice Looking Glass** (Recommended)
**Best overall choice for Ring deployments**

#### Features:
- **Native BIRD support** via birdc integration
- **API-first design** with REST endpoints
- **Modern web interface** with React frontend  
- **Multi-protocol support** (IPv4/IPv6)
- **Route filtering** and advanced search
- **JSON/text output** formats
- **Rate limiting** and access controls
- **Docker deployment** ready

#### Installation for AS 199036:

```bash
# Clone Alice Looking Glass
git clone https://github.com/alice-lg/alice-lg.git /opt/alice-lg
cd /opt/alice-lg

# Create configuration
cat > /etc/alice-lg/alice.conf << 'EOF'
[server]
listen_http = "0.0.0.0:7340"
enable_prefix_lookup = true
enable_neighbors_status_refresh = true
neighbors_status_refresh_interval = 5
store_last_refresh = true

[housekeeping]
interval = 5
force_release_memory = true

[rejection]
no_export = ["NO_EXPORT", "GRACEFUL_SHUTDOWN"]
not_found = 404

[theme]
path = "/opt/alice-lg/ui/dist"
url_base = "/"

# BIRD Route Server Configuration  
[[sources]]
name = "AS199036 NLNOG Ring"
group = "NLNOG Ring Route Collectors"

[sources.bird]
config = "/etc/bird/bird.conf"
birdc = "/usr/sbin/birdc"
birdc_socket = "/run/bird/bird.ctl"
timezone = "UTC"
server_time = "2006-01-02T15:04:05Z07:00"
server_time_short = "2006-01-02 15:04:05"
server_time_ext = "Mon, 02 Jan 2006 15:04:05 -0700"

# Pagination
[sources.bird.columns]
routes = ["network", "gateway", "interface", "metric", "as_path", "age"]
show_last_updated = true

# Filtering
[sources.bird.blackholes]
# Blackhole detection regex
communities = [".*:666$"]

# AS-specific settings
[sources.bird.routeservers]
as199036 = {
    "name": "AS 199036 NLNOG Ring Collector",
    "group": "Ring Collectors",
    "api_base": "",
    "neighbors_refresh_timeout": 120,
    "routes_refresh_timeout": 300
}
EOF

# Build Alice LG
make build

# Create systemd service
cat > /etc/systemd/system/alice-lg.service << 'EOF'
[Unit]
Description=Alice Looking Glass for AS 199036
Documentation=https://github.com/alice-lg/alice-lg
After=network.target bird.service
Requires=bird.service

[Service]
Type=simple
User=alice-lg
Group=alice-lg
WorkingDirectory=/opt/alice-lg
Environment=ALICE_CONFIG=/etc/alice-lg/alice.conf
ExecStart=/opt/alice-lg/bin/alice-lg-linux-amd64
Restart=always
RestartSec=10

# Performance settings
Nice=-5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# Create user and start service
useradd -r -s /bin/false alice-lg
systemctl enable alice-lg
systemctl start alice-lg
```

### 2. **Bird-LG (by Shuanglei Tao)**
**Lightweight Python-based solution**

#### Features:
- **Direct BIRD integration** using birdc
- **Clean web interface** with Bootstrap
- **IPv4/IPv6 support** 
- **Route lookup** and BGP queries
- **Lightweight** and fast
- **Easy to customize**

#### Installation:

```bash
# Install dependencies
apt install python3 python3-pip python3-venv nginx

# Clone and setup
git clone https://github.com/shuanglei/bird-lg.git /opt/bird-lg
cd /opt/bird-lg

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure for AS 199036
cat > /opt/bird-lg/lg.cfg << 'EOF'
# Bird-LG Configuration for AS 199036

[general]
name = AS 199036 NLNOG Ring Looking Glass
description = Route Collector for NLNOG Ring Network
location = NLNOG Ring Infrastructure
contact = noc@as199036.net
logo = /static/logo.png

[bird]
socket = /run/bird/bird.ctl
config_file = /etc/bird/bird.conf

[web]
listen = 0.0.0.0
port = 5000
workers = 4
timeout = 30

[features]
enable_ipv6 = true
enable_bgp_map = true
enable_traceroute = false  # Disable for security
enable_ping = false        # Disable for security
max_prefix_length_ipv4 = 32
max_prefix_length_ipv6 = 128

[rate_limit]
requests_per_minute = 60
burst = 10

[display]
show_as_names = true
show_communities = true
show_large_communities = true
routes_per_page = 50
EOF

# Create systemd service
cat > /etc/systemd/system/bird-lg.service << 'EOF'
[Unit]
Description=Bird Looking Glass for AS 199036
After=network.target bird.service
Requires=bird.service

[Service]
Type=simple
User=bird-lg
Group=bird-lg
WorkingDirectory=/opt/bird-lg
Environment=FLASK_APP=lg.py
Environment=FLASK_ENV=production
ExecStart=/opt/bird-lg/venv/bin/python lg.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create user and permissions
useradd -r -s /bin/false bird-lg
chown -R bird-lg:bird-lg /opt/bird-lg
usermod -a -G bird bird-lg  # Access to BIRD socket

systemctl enable bird-lg
systemctl start bird-lg
```

### 3. **Hyperglass**
**Enterprise-grade looking glass solution**

#### Features:
- **Modern React UI** with dark/light themes
- **Full BIRD support** with advanced queries
- **API-first architecture** with GraphQL
- **Multi-device responsive** design
- **Advanced filtering** and search
- **Customizable branding**
- **Rate limiting** and security features
- **Prometheus metrics** integration

#### Installation:

```bash
# Install via pip
pip3 install hyperglass[production]

# Create configuration directory
mkdir -p /etc/hyperglass

# Generate initial config
hyperglass setup

# Configure for AS 199036
cat > /etc/hyperglass/hyperglass.yaml << 'EOF'
debug: false
developer_mode: false

web:
  listen_address: "0.0.0.0"
  listen_port: 8001

branding:
  site_title: "AS 199036 NLNOG Ring Looking Glass"
  site_description: "Route Collector for NLNOG Ring Network"
  organization: "AS 199036"
  
logging:
  http_log: "/var/log/hyperglass/http.log"
  app_log: "/var/log/hyperglass/app.log"

cache:
  redis:
    host: "localhost"
    port: 6379
    database: 1

queries:
  - name: "bgp_route"
    display_name: "BGP Route"
    enable: true
  - name: "bgp_community"  
    display_name: "BGP Community"
    enable: true
  - name: "bgp_aspath"
    display_name: "BGP AS Path"
    enable: true

devices:
  - name: "as199036-collector"
    display_name: "AS 199036 Route Collector"
    location: "NLNOG Ring"
    group: "Collectors"
    nos: "bird"
    structured_output: true
    
    credential:
      username: "hyperglass"
      
    directives:
      - field: "bgp_route"
        commands:
          ipv4: "show route for {target}"
          ipv6: "show route for {target}"
      - field: "bgp_community"
        commands:
          ipv4: "show route where bgp_community ~ [({target})]"
          ipv6: "show route where bgp_community ~ [({target})]"
      - field: "bgp_aspath"
        commands:
          ipv4: "show route where bgp_path ~ [= * {target} * =]"
          ipv6: "show route where bgp_path ~ [= * {target} * =]"

    connection:
      host: "localhost"
      port: 22
      timeout: 30
      
    output:
      format: "json"
      structure:
        - name: "network"
          pattern: '(\S+)\s+via\s+(\S+)'
        - name: "next_hop"
          pattern: 'via\s+(\S+)'
        - name: "as_path"
          pattern: 'BGP\.as_path:\s+(.+)'
EOF

# Install Redis for caching
apt install redis-server
systemctl enable redis-server
systemctl start redis-server

# Create user
useradd -r -s /bin/false hyperglass

# Create systemd service
systemctl enable hyperglass
systemctl start hyperglass
```

### 4. **Custom BIRD API Solution**
**Tailored for Ring requirements**

#### Features:
- **Direct birdc integration**
- **RESTful API** for automation
- **Lightweight** Python Flask app
- **Customizable** for Ring-specific needs
- **JSON output** for programmatic access

#### Implementation:

```python
#!/usr/bin/env python3
# AS 199036 Custom BIRD Looking Glass API
# /opt/as199036-lg/app.py

from flask import Flask, request, jsonify, render_template
import subprocess
import json
import re
from datetime import datetime

app = Flask(__name__)

BIRD_SOCKET = "/run/bird/bird.ctl"
BIRDC_PATH = "/usr/sbin/birdc"

class BirdAPI:
    def __init__(self):
        self.socket = BIRD_SOCKET
        self.birdc = BIRDC_PATH
    
    def execute_command(self, command):
        """Execute birdc command and return output"""
        try:
            cmd = [self.birdc, "-s", self.socket, command]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return {
                "success": True,
                "output": result.stdout,
                "error": result.stderr if result.stderr else None
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def show_protocols(self):
        """Get BGP protocol status"""
        result = self.execute_command("show protocols")
        if not result["success"]:
            return result
        
        protocols = []
        for line in result["output"].split('\n'):
            if 'BGP' in line and ('up' in line or 'down' in line):
                parts = line.split()
                if len(parts) >= 6:
                    protocols.append({
                        "name": parts[0],
                        "protocol": parts[1], 
                        "table": parts[2],
                        "state": parts[3],
                        "since": parts[4],
                        "info": " ".join(parts[5:])
                    })
        
        return {"success": True, "protocols": protocols}
    
    def show_route(self, prefix=None, protocol=None, limit=100):
        """Show routes with optional filtering"""
        if prefix:
            cmd = f"show route for {prefix}"
        elif protocol:
            cmd = f"show route protocol {protocol}"
        else:
            cmd = "show route"
        
        if limit:
            cmd += f" | head -{limit}"
        
        result = self.execute_command(cmd)
        if not result["success"]:
            return result
        
        routes = self.parse_routes(result["output"])
        return {"success": True, "routes": routes}
    
    def parse_routes(self, output):
        """Parse BIRD route output into structured data"""
        routes = []
        current_route = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # New route entry
            if re.match(r'^\d+\.\d+\.\d+\.\d+/', line) or re.match(r'^[0-9a-f:]+:/', line):
                if current_route:
                    routes.append(current_route)
                
                parts = line.split()
                current_route = {
                    "network": parts[0],
                    "attributes": {}
                }
                
                # Parse next hop if present
                if "via" in line:
                    current_route["next_hop"] = line.split("via")[1].split()[0]
            
            # Parse BGP attributes
            elif current_route and line.startswith("BGP."):
                attr_match = re.match(r'BGP\.(\w+):\s*(.+)', line)
                if attr_match:
                    attr_name = attr_match.group(1)
                    attr_value = attr_match.group(2)
                    current_route["attributes"][attr_name] = attr_value
        
        if current_route:
            routes.append(current_route)
        
        return routes

# Initialize BIRD API
bird_api = BirdAPI()

@app.route('/')
def index():
    """Main looking glass page"""
    return render_template('index.html')

@app.route('/api/protocols')
def api_protocols():
    """Get BGP protocol status"""
    result = bird_api.show_protocols()
    return jsonify(result)

@app.route('/api/routes')
def api_routes():
    """Get routes with optional filtering"""
    prefix = request.args.get('prefix')
    protocol = request.args.get('protocol')
    limit = int(request.args.get('limit', 100))
    
    result = bird_api.show_route(prefix=prefix, protocol=protocol, limit=limit)
    return jsonify(result)

@app.route('/api/lookup/<path:query>')
def api_lookup(query):
    """Lookup specific route or AS"""
    if re.match(r'^\d+$', query):
        # AS number lookup
        result = bird_api.execute_command(f"show route where bgp_path ~ [= * {query} * =]")
    else:
        # Prefix lookup
        result = bird_api.execute_command(f"show route for {query}")
    
    return jsonify(result)

@app.route('/api/summary')  
def api_summary():
    """Get summary statistics"""
    ipv4_result = bird_api.execute_command("show route count")
    ipv6_result = bird_api.execute_command("show route ipv6 count")
    protocol_result = bird_api.show_protocols()
    
    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "ipv4_routes": 0,
        "ipv6_routes": 0,
        "bgp_sessions": {"up": 0, "down": 0}
    }
    
    # Parse route counts
    if ipv4_result["success"]:
        match = re.search(r'(\d+) of \d+ routes', ipv4_result["output"])
        if match:
            summary["ipv4_routes"] = int(match.group(1))
    
    if ipv6_result["success"]:
        match = re.search(r'(\d+) of \d+ routes', ipv6_result["output"])
        if match:
            summary["ipv6_routes"] = int(match.group(1))
    
    # Count BGP sessions
    if protocol_result["success"]:
        for protocol in protocol_result["protocols"]:
            if protocol["state"] == "up":
                summary["bgp_sessions"]["up"] += 1
            else:
                summary["bgp_sessions"]["down"] += 1
    
    return jsonify(summary)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

#### HTML Template (`templates/index.html`):

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AS 199036 NLNOG Ring Looking Glass</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .route-table { font-family: monospace; font-size: 0.9em; }
        .status-up { color: #28a745; }
        .status-down { color: #dc3545; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-primary">
        <div class="container">
            <span class="navbar-brand">AS 199036 NLNOG Ring Looking Glass</span>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header">
                        <h5>Route Lookup</h5>
                    </div>
                    <div class="card-body">
                        <form id="lookupForm">
                            <div class="row">
                                <div class="col-md-8">
                                    <input type="text" class="form-control" id="queryInput" 
                                           placeholder="Enter IP address, prefix, or AS number">
                                </div>
                                <div class="col-md-4">
                                    <button type="submit" class="btn btn-primary">Lookup</button>
                                </div>
                            </div>
                        </form>
                        
                        <div id="results" class="mt-3"></div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="card">
                    <div class="card-header">
                        <h6>Summary</h6>
                    </div>
                    <div class="card-body" id="summary">
                        <div class="text-center">
                            <div class="spinner-border" role="status"></div>
                        </div>
                    </div>
                </div>
                
                <div class="card mt-3">
                    <div class="card-header">
                        <h6>BGP Sessions</h6>
                    </div>
                    <div class="card-body" id="protocols">
                        <div class="text-center">
                            <div class="spinner-border" role="status"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Load summary data
        fetch('/api/summary')
            .then(response => response.json())
            .then(data => {
                document.getElementById('summary').innerHTML = `
                    <div class="row text-center">
                        <div class="col-6">
                            <h4>${data.ipv4_routes.toLocaleString()}</h4>
                            <small>IPv4 Routes</small>
                        </div>
                        <div class="col-6">
                            <h4>${data.ipv6_routes.toLocaleString()}</h4>
                            <small>IPv6 Routes</small>
                        </div>
                    </div>
                    <hr>
                    <div class="row text-center">
                        <div class="col-6">
                            <h5 class="status-up">${data.bgp_sessions.up}</h5>
                            <small>Sessions Up</small>
                        </div>
                        <div class="col-6">
                            <h5 class="status-down">${data.bgp_sessions.down}</h5>
                            <small>Sessions Down</small>
                        </div>
                    </div>
                `;
            });

        // Load protocol data
        fetch('/api/protocols')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    let html = '<div class="protocol-list" style="max-height: 300px; overflow-y: auto;">';
                    data.protocols.slice(0, 10).forEach(protocol => {
                        const statusClass = protocol.state === 'up' ? 'status-up' : 'status-down';
                        html += `
                            <div class="d-flex justify-content-between align-items-center py-1">
                                <small>${protocol.name}</small>
                                <span class="badge bg-secondary ${statusClass}">${protocol.state}</span>
                            </div>
                        `;
                    });
                    html += '</div>';
                    document.getElementById('protocols').innerHTML = html;
                }
            });

        // Handle form submission
        document.getElementById('lookupForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const query = document.getElementById('queryInput').value;
            if (!query) return;

            document.getElementById('results').innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';

            fetch(`/api/lookup/${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('results').innerHTML = `
                            <pre class="route-table bg-light p-3 rounded">${data.output}</pre>
                        `;
                    } else {
                        document.getElementById('results').innerHTML = `
                            <div class="alert alert-danger">Error: ${data.error}</div>
                        `;
                    }
                });
        });
    </script>
</body>
</html>
```

## Nginx Configuration for All Solutions

```nginx
# /etc/nginx/sites-available/as199036-lg
server {
    listen 80;
    server_name lg.as199036.net;

    location / {
        # For Alice Looking Glass
        proxy_pass http://127.0.0.1:7340;
        
        # For Bird-LG or Custom API
        # proxy_pass http://127.0.0.1:5000;
        
        # For Hyperglass
        # proxy_pass http://127.0.0.1:8001;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting
        limit_req zone=lg burst=10 nodelay;
    }
    
    # API endpoints with higher limits for automation
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # JSON responses
        proxy_set_header Accept application/json;
        add_header Content-Type application/json;
        
        # CORS for web apps
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type, Authorization";
    }
}

# Rate limiting configuration
http {
    limit_req_zone $binary_remote_addr zone=lg:10m rate=5r/s;
}
```

## Ansible Playbook for Looking Glass Deployment

```yaml
---
- name: Deploy BIRD Looking Glass for AS 199036
  hosts: ring_collectors
  become: yes
  
  vars:
    looking_glass_solution: "alice-lg"  # alice-lg, bird-lg, hyperglass, custom
    lg_domain: "lg.as199036.net"
    
  tasks:
    - name: Install dependencies
      apt:
        name:
          - nginx
          - python3
          - python3-pip
          - git
          - redis-server
        state: present
        update_cache: yes

    - name: Deploy Alice Looking Glass
      when: looking_glass_solution == "alice-lg"
      block:
        - name: Clone Alice LG repository
          git:
            repo: https://github.com/alice-lg/alice-lg.git
            dest: /opt/alice-lg
            
        - name: Create Alice LG user
          user:
            name: alice-lg
            system: yes
            shell: /bin/false
            
        - name: Deploy Alice LG configuration
          template:
            src: alice.conf.j2
            dest: /etc/alice-lg/alice.conf
            
        - name: Build Alice LG
          command: make build
          args:
            chdir: /opt/alice-lg
            
        - name: Deploy Alice LG systemd service
          template:
            src: alice-lg.service.j2
            dest: /etc/systemd/system/alice-lg.service
          notify: restart alice-lg

    - name: Configure Nginx
      template:
        src: nginx-lg.conf.j2
        dest: /etc/nginx/sites-available/{{ lg_domain }}
      notify: restart nginx
      
    - name: Enable Nginx site
      file:
        src: /etc/nginx/sites-available/{{ lg_domain }}
        dest: /etc/nginx/sites-enabled/{{ lg_domain }}
        state: link
      notify: restart nginx

    - name: Start and enable services
      systemd:
        name: "{{ item }}"
        state: started
        enabled: yes
        daemon_reload: yes
      loop:
        - nginx
        - redis-server
        - "{{ looking_glass_solution }}"

  handlers:
    - name: restart nginx
      systemd:
        name: nginx
        state: restarted
        
    - name: restart alice-lg
      systemd:
        name: alice-lg
        state: restarted
```

## Recommendation for AS 199036

**For your NLNOG Ring setup, I recommend Alice Looking Glass** because:

1. **Ring Integration**: Designed for route server/collector deployments
2. **BIRD Native**: Built specifically for BIRD integration
3. **Performance**: Handles large routing tables efficiently
4. **API First**: Great for automation and integration
5. **Modern UI**: Clean, responsive interface
6. **Community**: Active development and Ring community support

The migration from `bgplgd` to Alice Looking Glass will provide:
- Better performance with your 160M+ routes
- Full utilization of BIRD's capabilities
- Modern web interface for users
- REST API for automation
- Better integration with Ring infrastructure

Would you like me to create detailed deployment instructions for any specific solution, or help you customize the Alice Looking Glass configuration for your Ring setup?
