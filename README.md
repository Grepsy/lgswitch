# LG TV Auto-Switcher

Automatically switch your LG OLED TV input based on USB keyboard connection status. Perfect for KVM switch setups where you want the TV to follow your computer selection.

## Overview

This tool monitors your USB keyboard connection and automatically switches your LG WebOS TV between HDMI inputs:
- **Keyboard connected** → Switches to HDMI 2
- **Keyboard disconnected** → Switches to HDMI 3

## Features

- Monitors specific USB keyboard by Vendor/Product ID
- Automatic TV input switching via LG WebOS API
- Optional TV screen power control (turn on when keyboard connects)
- Runs as background systemd service
- Auto-start on boot
- Logging for debugging
- State tracking to avoid redundant switches

## Requirements

- **Hardware:**
  - LG OLED TV (any WebOS TV)
  - Linux computer on same network as TV
  - USB keyboard (or KVM switch)

- **Software:**
  - Python 3.7+
  - pip (Python package manager)
  - systemd (for background service)

## Installation

1. **Clone or download this repository:**
   ```bash
   git clone https://github.com/Grepsy/lgswitch.git
   cd lgswitch
   ```

2. **Create a Python virtual environment:**
   ```bash
   python3 -m venv venv
   ```

3. **Install Python dependencies:**
   ```bash
   ./venv/bin/pip install -r requirements.txt
   ```

   This installs:
   - `bscpylgtv` - LG WebOS TV control library
   - `pyudev` - USB device monitoring

## Setup

Run the interactive setup script to configure the application:

```bash
./venv/bin/python setup.py
```

The setup script will:

1. **Find your TV's IP address**
   - You'll need to provide this manually
   - Check your router's DHCP list, TV network settings, or use `avahi-browse -t _webostv._tcp`

2. **Pair with your TV**
   - A pairing prompt will appear on your TV screen
   - Accept it using your TV remote
   - The pairing key is stored for future use

3. **Test TV connection**
   - Automatically switches between HDMI 2 and HDMI 3 to verify it works

4. **Detect your keyboard**
   - Lists all connected USB keyboards
   - Select the one you want to monitor (e.g., the one connected through your KVM)

5. **Save configuration**
   - Creates `~/.config/lgswitch/config.json`

## Usage

### Running Manually

To test the monitor:

```bash
./venv/bin/python lgswitch.py
```

This will:
- Check if your keyboard is currently connected
- Switch TV to appropriate input
- Monitor for keyboard connect/disconnect events
- Log all activity to console and `~/.config/lgswitch/lgswitch.log`

Press `Ctrl+C` to stop.

### Installing as systemd Service

For automatic startup and background operation:

1. **Create a customized service file with the correct path:**
   ```bash
   mkdir -p ~/.config/systemd/user
   INSTALL_DIR=$(pwd)
   sed "s|INSTALL_PATH|$INSTALL_DIR|g" lgswitch.service > ~/.config/systemd/user/lgswitch.service
   ```

2. **Reload systemd configuration:**
   ```bash
   systemctl --user daemon-reload
   ```

3. **Enable and start the service:**
   ```bash
   systemctl --user enable lgswitch.service
   systemctl --user start lgswitch.service
   ```

4. **Check service status:**
   ```bash
   systemctl --user status lgswitch.service
   ```

5. **View logs:**
   ```bash
   journalctl --user -u lgswitch.service -f
   ```

6. **Enable lingering (start service at boot, even before login):**
   ```bash
   sudo loginctl enable-linger $USER
   ```

### Service Management Commands

```bash
# Start service
systemctl --user start lgswitch.service

# Stop service
systemctl --user stop lgswitch.service

# Restart service
systemctl --user restart lgswitch.service

# Disable service
systemctl --user disable lgswitch.service

# View real-time logs
journalctl --user -u lgswitch.service -f
```

## Configuration

Configuration is stored in `~/.config/lgswitch/config.json`:

```json
{
  "tv_ip": "192.168.1.100",
  "keyboard": {
    "vendor_id": "046d",
    "model_id": "c52b",
    "name": "Logitech Keyboard"
  },
  "hdmi": {
    "connected": "com.webos.app.hdmi2",
    "disconnected": "com.webos.app.hdmi3"
  },
  "screen": {
    "turn_on_when_connected": true
  }
}
```

The TV pairing key is stored separately in `~/.aiopylgtv.sqlite` and managed automatically.

### Customizing HDMI Inputs

To change which HDMI inputs are used, edit the `hdmi` section:

- `com.webos.app.hdmi1` - HDMI 1
- `com.webos.app.hdmi2` - HDMI 2
- `com.webos.app.hdmi3` - HDMI 3
- `com.webos.app.hdmi4` - HDMI 4

Example - switch between HDMI 1 and HDMI 4:
```json
"hdmi": {
  "connected": "com.webos.app.hdmi1",
  "disconnected": "com.webos.app.hdmi4"
}
```

After editing, restart the service:
```bash
systemctl --user restart lgswitch.service
```

### Screen Power Control

The application can automatically turn on your TV screen when the keyboard connects. This is enabled by default.

To disable screen power control, edit the `screen` section:
```json
"screen": {
  "turn_on_when_connected": false
}
```

This feature is useful if:
- Your TV screen is in standby/screen-off mode
- You want the TV to wake up when you switch to this computer
- You're using the TV with multiple devices

**Note:** The screen will only turn ON when the keyboard connects. It will not turn off when disconnected - only the HDMI input will switch.

After editing, restart the service:
```bash
systemctl --user restart lgswitch.service
```

## Troubleshooting

### Can't find TV IP address

**Option 1: Check router**
- Log into your router's admin interface
- Look for DHCP client list or connected devices
- Find device labeled "LG TV" or similar

**Option 2: Use avahi-browse**
```bash
sudo apt install avahi-utils
avahi-browse -t _webostv._tcp
```

**Option 3: Check TV settings**
- On TV: Settings → Network → Wi-Fi Connection (or Wired Connection)
- Look for IP Address

### Pairing fails

- Ensure TV is on and connected to network
- Verify TV and computer are on same network/subnet
- Check no firewall is blocking ports 3000/3001
- Make sure you accept the pairing prompt on TV screen quickly

### Keyboard not detected

**Find your keyboard's USB IDs:**
```bash
lsusb
```

Look for your keyboard in the output:
```
Bus 001 Device 005: ID 046d:c52b Logitech, Inc. Unifying Receiver
```

The format is `vendor_id:model_id`. In this example:
- Vendor ID: `046d`
- Model ID: `c52b`

Manually edit `~/.config/lgswitch/config.json` with these values if needed.

### TV not switching

**Check logs:**
```bash
tail -f ~/.config/lgswitch/lgswitch.log
```

Or if running as service:
```bash
journalctl --user -u lgswitch.service -f
```

**Common issues:**
- TV is off or asleep
- TV IP address changed (check router DHCP)
- Network connectivity issues
- Pairing key expired (re-run `setup.py`)

### Service won't start at boot

Enable lingering for your user:
```bash
sudo loginctl enable-linger $USER
```

This allows your user services to start even before you log in.

## How It Works

1. **USB Monitoring**: Uses `pyudev` to monitor Linux kernel udev events for USB device additions/removals
2. **Device Filtering**: Filters events to match only your specific keyboard (by USB Vendor/Product ID)
3. **State Tracking**: Maintains internal state to avoid redundant TV commands
4. **TV Control**: Uses `bscpylgtv` library to communicate with LG TV over WebSocket (WebOS API)
5. **Input Switching**: Sends app launch commands to switch HDMI inputs

## Project Structure

```
lgswitch/
├── lgswitch.py          # Main monitoring daemon
├── setup.py             # Interactive setup script
├── requirements.txt     # Python dependencies
├── lgswitch.service     # systemd service file
└── README.md           # This file

~/.config/lgswitch/
├── config.json         # Configuration (created by setup)
└── lgswitch.log        # Application logs
```

## Advanced Usage

### Testing keyboard detection

```bash
# List USB devices
lsusb

# Monitor USB events in real-time
udevadm monitor --subsystem-match=usb --property

# Then plug/unplug your keyboard to see events
```

### Debugging

Enable Python logging at DEBUG level by editing `lgswitch.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    ...
)
```

## License

This project is provided as-is for personal use.

## Credits

- Uses [bscpylgtv](https://github.com/chros73/bscpylgtv) for LG TV control
- Uses [pyudev](https://pyudev.readthedocs.io/) for USB device monitoring
