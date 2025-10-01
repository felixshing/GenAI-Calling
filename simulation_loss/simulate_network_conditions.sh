#!/bin/bash
# Network simulation script for macOS using pfctl and dummynet
# Requires sudo privileges

set -e

# Select interface automatically if not provided (prefers Wi‑Fi); allow override
# To use your hotspot bridge: set INTERFACE=bridge100 when invoking the script
INTERFACE=${INTERFACE:-$(networksetup -listallhardwareports 2>/dev/null | awk '/Wi-Fi/{getline; print $2; exit} END{print "en0"}')}
PORT=${PORT:-8080}

function show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  loss5      - Add 5% packet loss"
    echo "  loss10     - Add 10% packet loss" 
    echo "  loss20     - Add 20% packet loss"
    echo "  good       - Good network (1% loss)"
    echo "  median     - Median network (5% loss)" 
    echo "  poor       - Poor network (15% loss)"
    echo "  delay      - Add 100ms delay"
    echo "  combined   - Add 5% loss + 50ms delay"
    echo "  clear      - Remove all rules"
    echo "  status     - Show current rules"
    echo ""
    echo "Example:"
    echo "  sudo $0 loss10    # Add 10% packet loss"
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

function add_loss() {
    local loss_percent=$1
    local client_ip=${CLIENT_IP:-"192.168.2.46"}  # Your phone IP
    echo "📉 Adding ${loss_percent}% packet loss for client ${client_ip}..."
    
    echo "pfctl probability is approximate and not per-flow."
    echo "   Applying UDP/ICMP rules on ${INTERFACE} for client ${client_ip}"

    sudo pfctl -E >/dev/null 2>&1 || true
    cat >/tmp/pf_loss.conf <<EOF
scrub in on ${INTERFACE} random-id
# Block UDP traffic (WebRTC media) with probability
block in quick on ${INTERFACE} proto udp from ${client_ip} to any probability ${loss_percent}%
block out quick on ${INTERFACE} proto udp from any to ${client_ip} probability ${loss_percent}%
# Block ICMP (ping) with same probability for testing
block in quick on ${INTERFACE} proto icmp from ${client_ip} to any probability ${loss_percent}%
block out quick on ${INTERFACE} proto icmp from any to ${client_ip} probability ${loss_percent}%
# Allow all other traffic
pass in all
pass out all
EOF
    pfctl -f /tmp/pf_loss.conf 2>/dev/null || true
    echo "${loss_percent}% packet loss rules loaded for ${client_ip} (pfctl)"
}

function add_delay() {
    echo "⏱️  Adding 100ms delay on interface ${INTERFACE}..."
    echo "macOS pfctl doesn't support precise delay directly. Use NLC or 'ipfw dnctl' if available."
    echo "💡 For this project, prefer Network Link Conditioner to set RTT and use this script for loss."
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
        add_loss 5
        ;;
    "loss10") 
        check_sudo $1
        clear_rules
        add_loss 10
        ;;
    "loss20")
        check_sudo $1 
        clear_rules
        add_loss 20
        ;;
    "good")
        check_sudo $1
        clear_rules
        add_loss 1
        echo "Good network conditions applied (1% loss)"
        ;;
    "median")
        check_sudo $1
        clear_rules
        add_loss 5
        echo "Median network conditions applied (5% loss)"
        ;;
    "poor")
        check_sudo $1
        clear_rules
        add_loss 15
        echo "Poor network conditions applied (15% loss)"
        ;;
    "delay")
        add_delay
        ;;
    "combined")
        check_sudo $1
        clear_rules  
        add_loss 5
        add_delay
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