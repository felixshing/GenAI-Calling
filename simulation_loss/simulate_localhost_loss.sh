#!/bin/bash
# Network simulation script for localhost connections on macOS
# Uses pfctl to affect loopback traffic

set -e

function show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  loss5      - Add 5% packet loss to localhost"
    echo "  loss10     - Add 10% packet loss to localhost"
    echo "  loss20     - Add 20% packet loss to localhost"
    echo "  loss50     - Add 50% packet loss to localhost"
    echo "  loss80     - Add 80% packet loss to localhost"
    echo "  loss100    - Add 100% packet loss to localhost (complete block)"
    echo "  clear      - Remove all rules"
    echo "  status     - Show current rules"
    echo ""
    echo "Example:"
    echo "  sudo $0 loss10    # Add 10% packet loss to localhost"
    echo "  sudo $0 clear     # Remove all rules"
}

function check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script requires sudo privileges"
        echo "Run: sudo $0 $1"
        exit 1
    fi
}

function clear_rules() {
    echo "🧹 Clearing all pfctl rules..."
    pfctl -f /etc/pf.conf 2>/dev/null || true
    pfctl -d 2>/dev/null || true
    echo "Rules cleared"
}

function add_localhost_loss() {
    local loss_percent=$1
    echo "📉 Adding ${loss_percent}% packet loss to localhost traffic..."
    
    sudo pfctl -E >/dev/null 2>&1 || true
    cat >/tmp/pf_localhost_loss.conf <<EOF
# Block UDP traffic on high ports (WebRTC media) with probability
# WebRTC typically uses ports 1024-65535 for media
block in quick inet proto udp from 127.0.0.1 port > 1023 to any probability ${loss_percent}%
block out quick inet proto udp from any to 127.0.0.1 port > 1023 probability ${loss_percent}%
block in quick inet proto udp from 127.0.0.1 to any port > 1023 probability ${loss_percent}%
block out quick inet proto udp from any port > 1023 to 127.0.0.1 probability ${loss_percent}%
# Also try blocking on loopback interface
block in quick on lo0 inet proto udp probability ${loss_percent}%
block out quick on lo0 inet proto udp probability ${loss_percent}%
# Allow all other traffic
pass in all
pass out all
EOF
    pfctl -f /tmp/pf_localhost_loss.conf 2>/dev/null || true
    echo "${loss_percent}% packet loss rules loaded for localhost (pfctl)"
}

function show_status() {
    echo "📊 Current pfctl status:"
    pfctl -s rules 2>/dev/null || echo "No rules active"
}

# Main logic
case "${1:-help}" in
    "loss5")
        check_sudo $1
        clear_rules
        add_localhost_loss 5
        ;;
    "loss10") 
        check_sudo $1
        clear_rules
        add_localhost_loss 10
        ;;
    "loss20")
        check_sudo $1 
        clear_rules
        add_localhost_loss 20
        ;;
    "loss50")
        check_sudo $1 
        clear_rules
        add_localhost_loss 50
        ;;
    "loss80")
        check_sudo $1 
        clear_rules
        add_localhost_loss 80
        ;;
    "loss100")
        check_sudo $1 
        clear_rules
        add_localhost_loss 100
        ;;
    "clear")
        check_sudo $1
        clear_rules
        ;;
    "status")
        show_status
        ;;
    "help"|*)
        show_help
        ;;
esac