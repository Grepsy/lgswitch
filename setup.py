#!/usr/bin/env python3
"""
Setup script for LG TV Auto-Switcher
Discovers TV, pairs with it, and detects keyboard USB IDs
"""

import asyncio
import json
import os
import sys
import time
import pyudev
from pathlib import Path

try:
    from bscpylgtv import WebOsClient, StorageSqliteDict
except ImportError:
    print("Error: bscpylgtv not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


CONFIG_DIR = Path.home() / ".config" / "lgswitch"
CONFIG_FILE = CONFIG_DIR / "config.json"


def discover_tv():
    """Attempt to discover LG TV on the network"""
    print("\n=== TV Discovery ===")
    print("Note: Automatic discovery is not implemented in bscpylgtv.")
    print("You'll need to find your TV's IP address manually.")
    print("\nOptions:")
    print("1. Check your router's DHCP client list")
    print("2. Use: avahi-browse -t _webostv._tcp")
    print("3. Check TV settings: Network -> Wi-Fi/Ethernet -> IP Address")

    while True:
        tv_ip = input("\nEnter your TV's IP address: ").strip()
        if tv_ip:
            return tv_ip
        print("IP address cannot be empty.")


async def pair_with_tv(tv_ip):
    """Pair with the TV"""
    print("\n=== TV Pairing ===")
    print(f"Connecting to TV at {tv_ip}...")
    print("\n⚠️  IMPORTANT: You will see a pairing prompt on your TV screen.")
    print("    Please ACCEPT the pairing request when it appears!\n")

    # Create config directory
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Create and initialize storage
        storage_file = str(Path.home() / ".aiopylgtv.sqlite")
        storage = StorageSqliteDict(storage_file)
        await storage.async_init()

        # Create client with initialized storage
        client = await WebOsClient.create(tv_ip, storage=storage)
        await client.connect()

        # Verify connection was successful
        if client.client_key:
            print(f"✓ Successfully paired with TV!")
            await client.disconnect()
        else:
            print("✗ Failed to pair with TV")
            sys.exit(1)

    except Exception as e:
        print(f"✗ Error connecting to TV: {e}")
        print("\nTroubleshooting:")
        print("- Verify the TV is on and connected to the network")
        print("- Check the IP address is correct")
        print("- Ensure your computer and TV are on the same network")
        print("- Make sure no firewall is blocking the connection")
        sys.exit(1)


async def test_tv_connection(tv_ip):
    """Test the TV connection and try switching inputs"""
    print("\n=== Testing TV Connection ===")

    try:
        # Create and initialize storage
        storage_file = str(Path.home() / ".aiopylgtv.sqlite")
        storage = StorageSqliteDict(storage_file)
        await storage.async_init()

        # Create client with initialized storage
        client = await WebOsClient.create(tv_ip, storage=storage)
        await client.connect()

        print("✓ Connected to TV successfully!")

        # Try to get current input
        print("\nTesting HDMI switching...")
        print("Switching to HDMI 2...")
        await client.launch_app("com.webos.app.hdmi2")
        await asyncio.sleep(2)

        print("Switching to HDMI 3...")
        await client.launch_app("com.webos.app.hdmi3")
        await asyncio.sleep(2)

        print("✓ TV control test successful!")

        await client.disconnect()
        return True

    except Exception as e:
        print(f"✗ Error testing TV connection: {e}")
        return False


def detect_keyboards():
    """Detect all USB keyboards currently connected"""
    print("\n=== Keyboard Detection ===")
    print("Scanning for USB keyboards...\n")

    context = pyudev.Context()
    keyboards = []
    seen_keyboards = set()  # Track unique keyboards by vendor/model ID

    # Look for input devices with keyboard property
    for device in context.list_devices(subsystem='input'):
        # Check if it's a keyboard
        if device.get('ID_INPUT_KEYBOARD') == '1' and device.get('ID_BUS') == 'usb':
            vendor_id = device.get('ID_VENDOR_ID')
            model_id = device.get('ID_MODEL_ID')

            # Skip if we've already seen this keyboard
            if vendor_id and model_id:
                key = (vendor_id, model_id)
                if key in seen_keyboards:
                    continue
                seen_keyboards.add(key)

                vendor = device.get('ID_VENDOR', 'Unknown')
                model = device.get('ID_MODEL', 'Unknown')

                keyboards.append({
                    'vendor_id': vendor_id,
                    'model_id': model_id,
                    'vendor': vendor.replace('_', ' '),
                    'model': model.replace('_', ' '),
                    'device_path': device.device_path
                })

    if not keyboards:
        print("✗ No USB keyboards detected!")
        print("\nPlease ensure your keyboard is connected and try again.")
        sys.exit(1)

    # Display found keyboards
    print(f"Found {len(keyboards)} USB keyboard(s):\n")
    for i, kb in enumerate(keyboards, 1):
        print(f"{i}. {kb['vendor']} {kb['model']}")
        print(f"   Vendor ID: {kb['vendor_id']}, Product ID: {kb['model_id']}")
        print()

    # Let user select keyboard
    if len(keyboards) == 1:
        print("Using the only detected keyboard.")
        return keyboards[0]
    else:
        while True:
            try:
                choice = input(f"Select keyboard to monitor (1-{len(keyboards)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(keyboards):
                    return keyboards[idx]
                else:
                    print(f"Please enter a number between 1 and {len(keyboards)}")
            except (ValueError, KeyboardInterrupt):
                print("\nSetup cancelled.")
                sys.exit(1)


def save_config(tv_ip, keyboard):
    """Save configuration to file"""
    print("\n=== Saving Configuration ===")

    config = {
        "tv_ip": tv_ip,
        "keyboard": {
            "vendor_id": keyboard['vendor_id'],
            "model_id": keyboard['model_id'],
            "name": f"{keyboard['vendor']} {keyboard['model']}"
        },
        "hdmi": {
            "connected": "com.webos.app.hdmi2",
            "disconnected": "com.webos.app.hdmi3"
        },
        "screen": {
            "turn_on_when_connected": True
        }
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Configuration saved to: {CONFIG_FILE}")
    print(f"✓ TV pairing key stored in: ~/.aiopylgtv.sqlite")
    return config


async def async_main():
    """Main setup flow with async support"""
    print("=" * 60)
    print("LG TV Auto-Switcher Setup")
    print("=" * 60)

    # Check if config already exists
    if CONFIG_FILE.exists():
        print(f"\n⚠️  Configuration file already exists: {CONFIG_FILE}")
        response = input("Do you want to overwrite it? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("Setup cancelled.")
            sys.exit(0)

    # Step 1: Discover TV
    tv_ip = discover_tv()

    # Step 2: Pair with TV
    await pair_with_tv(tv_ip)

    # Step 3: Test TV connection
    await test_tv_connection(tv_ip)

    # Step 4: Detect keyboard
    keyboard = detect_keyboards()

    # Step 5: Save configuration
    config = save_config(tv_ip, keyboard)

    # Final summary
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  TV IP:           {config['tv_ip']}")
    print(f"  Keyboard:        {config['keyboard']['name']}")
    print(f"  Keyboard VID:    {config['keyboard']['vendor_id']}")
    print(f"  Keyboard PID:    {config['keyboard']['model_id']}")
    print(f"  When connected:  HDMI 2")
    print(f"  When disconnected: HDMI 3")

    print("\nNext steps:")
    print("  1. Run the monitor: ./venv/bin/python lgswitch.py")
    print("  2. Or install as service: see README.md")
    print()


def main():
    """Entry point that runs async main"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
