#!/usr/bin/env python3
"""
LG TV Auto-Switcher Monitor
Monitors USB keyboard connection and switches TV HDMI inputs automatically
"""

import asyncio
import json
import logging
import sys
import signal
import time
from pathlib import Path
from typing import Optional

try:
    import pyudev
    from bscpylgtv import WebOsClient, StorageSqliteDict
except ImportError as e:
    print(f"Error: Missing dependency - {e}")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)


CONFIG_DIR = Path.home() / ".config" / "lgswitch"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "lgswitch.log"


class TVSwitcher:
    """Manages TV connection and input switching"""

    def __init__(self, tv_ip: str, hdmi_connected: str, hdmi_disconnected: str, turn_on_screen: bool = True):
        self.tv_ip = tv_ip
        self.hdmi_connected = hdmi_connected
        self.hdmi_disconnected = hdmi_disconnected
        self.turn_on_screen = turn_on_screen
        self.client: Optional[WebOsClient] = None
        self.storage = None
        self.logger = logging.getLogger("TVSwitcher")
        self._cleanup_done = False

    async def initialize_storage(self):
        """Initialize storage once for reuse"""
        if not self.storage:
            storage_file = str(Path.home() / ".aiopylgtv.sqlite")
            self.storage = StorageSqliteDict(storage_file)
            await self.storage.async_init()
            self.logger.info(f"Storage initialized at {storage_file}")

    async def connect(self) -> bool:
        """Connect to the TV"""
        try:
            if self.client:
                return True

            self.logger.info(f"Connecting to TV at {self.tv_ip}...")

            # Initialize storage if not already done
            await self.initialize_storage()

            # Create client with persistent storage
            self.client = WebOsClient(self.tv_ip, storage=self.storage)
            await self.client.connect()
            self.logger.info("Connected to TV successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to TV: {e}")
            self.client = None
            return False

    async def disconnect(self):
        """Disconnect from TV"""
        if self.client:
            try:
                await self.client.disconnect()
                self.logger.info("Disconnected from TV")
            except Exception as e:
                self.logger.warning(f"Error disconnecting from TV: {e}")
            finally:
                self.client = None

    async def cleanup(self):
        """Clean up all resources"""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        await self.disconnect()

    async def switch_input(self, connected: bool) -> bool:
        """Switch TV input based on keyboard connection state"""
        hdmi_app = self.hdmi_connected if connected else self.hdmi_disconnected
        state_name = "connected" if connected else "disconnected"

        self.logger.info(f"Keyboard {state_name}, switching to {hdmi_app}")

        client = None
        try:
            # Initialize storage if not already done
            await self.initialize_storage()

            # Create fresh connection for this command
            self.logger.debug(f"Connecting to TV at {self.tv_ip}...")
            client = await WebOsClient.create(self.tv_ip, storage=self.storage)
            await client.connect()

            # Turn on screen if configured and keyboard connected
            if connected and self.turn_on_screen:
                try:
                    self.logger.info("Turning TV screen on")
                    await client.turn_screen_on()
                    self.logger.info("Successfully turned screen on")
                except Exception as e:
                    self.logger.warning(f"Could not turn screen on: {e}")
                    # Continue with HDMI switch even if screen control fails

            # Switch HDMI input
            await client.launch_app(hdmi_app)
            self.logger.info(f"Successfully switched to {hdmi_app}")

            # Disconnect immediately
            await client.disconnect()
            return True

        except Exception as e:
            self.logger.error(f"Failed to switch input: {e}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return False


class KeyboardMonitor:
    """Monitors USB keyboard connection events"""

    def __init__(self, vendor_id: str, model_id: str, keyboard_name: str, tv_switcher: TVSwitcher):
        self.vendor_id = vendor_id.lower()
        self.model_id = model_id.lower()
        self.keyboard_name = keyboard_name
        self.tv_switcher = tv_switcher
        self.logger = logging.getLogger("KeyboardMonitor")
        self.keyboard_connected = None  # Track current state (None = unknown)
        self.running = True
        self.loop = None
        self.last_event_time = 0  # For debouncing
        self.debounce_delay = 0.5  # 500ms debounce delay

    def is_target_keyboard(self, device) -> bool:
        """Check if device is our target keyboard"""
        # Must be a USB keyboard
        if device.get('ID_BUS') != 'usb':
            return False
        if device.get('ID_INPUT_KEYBOARD') != '1':
            return False

        # Check vendor and model IDs
        vendor_id = device.get('ID_VENDOR_ID', '').lower()
        model_id = device.get('ID_MODEL_ID', '').lower()
        return vendor_id == self.vendor_id and model_id == self.model_id

    async def check_initial_state(self):
        """Check if keyboard is currently connected at startup"""
        self.logger.info("Checking initial keyboard state...")

        context = pyudev.Context()
        # Check input devices for current keyboard state
        for device in context.list_devices(subsystem='input'):
            if device.get('ID_INPUT_KEYBOARD') == '1' and device.get('ID_BUS') == 'usb':
                vendor_id = device.get('ID_VENDOR_ID', '').lower()
                model_id = device.get('ID_MODEL_ID', '').lower()
                if vendor_id == self.vendor_id and model_id == self.model_id:
                    self.logger.info(f"Keyboard '{self.keyboard_name}' is currently connected")
                    self.keyboard_connected = True
                    await self.tv_switcher.switch_input(True)
                    return

        self.logger.info(f"Keyboard '{self.keyboard_name}' is not connected")
        self.keyboard_connected = False
        await self.tv_switcher.switch_input(False)

    def handle_device_event(self, action: str, device):
        """Handle USB device add/remove events"""
        # Only process our target keyboard
        if not self.is_target_keyboard(device):
            return

        # Debouncing: ignore events that occur too quickly after the last one
        current_time = time.time()
        if current_time - self.last_event_time < self.debounce_delay:
            return  # Silently ignore duplicate events
        self.last_event_time = current_time

        vendor = device.get('ID_VENDOR', 'Unknown')
        model = device.get('ID_MODEL', 'Unknown')

        if action == 'add':
            self.logger.info(f"USB keyboard connected: {vendor} {model}")
            if self.keyboard_connected is not True:
                self.keyboard_connected = True
                # Schedule the async switch in the event loop
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.tv_switcher.switch_input(True),
                        self.loop
                    )
            else:
                self.logger.debug("Keyboard already marked as connected, skipping switch")

        elif action == 'remove':
            self.logger.info(f"USB keyboard disconnected: {vendor} {model}")
            if self.keyboard_connected is not False:
                self.keyboard_connected = False
                # Schedule the async switch in the event loop
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.tv_switcher.switch_input(False),
                        self.loop
                    )
            else:
                self.logger.debug("Keyboard already marked as disconnected, skipping switch")

    async def start_monitoring(self):
        """Start monitoring USB events"""
        self.logger.info("Starting USB keyboard monitoring...")
        self.logger.info(f"Watching for: {self.keyboard_name}")
        self.logger.info(f"Vendor ID: {self.vendor_id}, Product ID: {self.model_id}")

        # Get the current event loop
        self.loop = asyncio.get_event_loop()

        # Check initial state
        await self.check_initial_state()

        # Set up monitor for input subsystem (where keyboard events happen)
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='input')
        monitor.start()

        self.logger.info("Monitor started. Waiting for keyboard events...")
        self.logger.info("Press Ctrl+C to stop")

        # Use non-blocking poll with timeout
        def poll_with_timeout():
            device = monitor.poll(timeout=0.5)
            return device

        # Monitor loop with periodic checks for shutdown
        while self.running:
            try:
                device = await self.loop.run_in_executor(None, poll_with_timeout)
                if device and device.action in ('add', 'remove'):
                    self.handle_device_event(device.action, device)
            except Exception as e:
                if self.running:  # Only log if we're not shutting down
                    self.logger.error(f"Error in monitor loop: {e}")
                break

        self.logger.info("Monitor loop exited")

    def stop(self):
        """Stop monitoring"""
        self.logger.info("Stopping monitor...")
        self.running = False


def load_config() -> dict:
    """Load configuration from file"""
    if not CONFIG_FILE.exists():
        print(f"Error: Configuration file not found: {CONFIG_FILE}")
        print("Please run setup.py first to configure the application.")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)


def setup_logging():
    """Set up logging to file and console"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger("Main")
    logger.info("=" * 60)
    logger.info("LG TV Auto-Switcher Monitor Starting")
    logger.info("=" * 60)

    return logger


async def async_main():
    """Main entry point with async support"""
    logger = setup_logging()

    # Load configuration
    logger.info(f"Loading configuration from {CONFIG_FILE}")
    config = load_config()

    # Initialize TV switcher
    tv_switcher = TVSwitcher(
        tv_ip=config['tv_ip'],
        hdmi_connected=config['hdmi']['connected'],
        hdmi_disconnected=config['hdmi']['disconnected'],
        turn_on_screen=config.get('screen', {}).get('turn_on_when_connected', True)
    )

    # Initialize keyboard monitor
    keyboard_monitor = KeyboardMonitor(
        vendor_id=config['keyboard']['vendor_id'],
        model_id=config['keyboard']['model_id'],
        keyboard_name=config['keyboard']['name'],
        tv_switcher=tv_switcher
    )

    # Get event loop for signal handling
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    # Set up async signal handlers
    def signal_handler():
        if not shutdown_event.is_set():
            logger.info("Received shutdown signal, shutting down gracefully...")
            keyboard_monitor.stop()
            shutdown_event.set()

    # Register signal handlers for SIGINT and SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start monitoring
    try:
        # Run monitoring until shutdown signal
        monitor_task = asyncio.create_task(keyboard_monitor.start_monitoring())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for either monitoring to complete or shutdown signal
        done, pending = await asyncio.wait(
            {monitor_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel any remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info("Shutdown sequence initiated")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Clean up resources
        await tv_switcher.cleanup()
        logger.info("Cleanup complete")

        # Remove signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    """Entry point that runs async main"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        # Should not reach here due to signal handlers, but just in case
        pass
    print("\nShutdown complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
