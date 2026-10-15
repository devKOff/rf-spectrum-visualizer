"""Hardware backend for nRF24L01+ radio using pyrf24 on Raspberry Pi 3B+."""

import time
import threading
import logging
import os
from typing import Optional, Tuple, Dict, Any
from contextlib import contextmanager

from config import ChannelConfig, ScanConfig, HardwareConfig
from exceptions import (
    HardwareError,
    RadioInitError,
    SPIError,
    RadioNotFoundError,
    InvalidChannelError,
)
from radio.base_radio import BaseRadio

logger = logging.getLogger("rf_visualizer.hardware")


class HardwareRadio(BaseRadio):
    """Hardware interface for nRF24L01+ via pyrf24 on Raspberry Pi 3B+.
    
    Pins: CE=GPIO25, CSN=GPIO8 (SPI CE0), SCK=GPIO11, MOSI=GPIO10, MISO=GPIO9
    """
    
    def __init__(
        self,
        channel_config: ChannelConfig,
        scan_config: ScanConfig,
        hardware_config: Optional[HardwareConfig] = None,
    ):
        self._channel_config = channel_config
        self._scan_config = scan_config
        self._hw_config = hardware_config or HardwareConfig()
        self._radio = None
        self._initialized = False
        self._lock = threading.RLock()
        self._current_channel = channel_config.start_channel
        self._pyrf24 = None
        self._pyrf24_available = False
        self._check_pyrf24()
    
    def _check_pyrf24(self) -> None:
        """Check if pyrf24 is available."""
        try:
            import pyrf24
            self._pyrf24 = pyrf24
            self._pyrf24_available = True
            version = getattr(pyrf24, '__version__', 'unknown')
            logger.info(f"pyrf24 available: {version}")
        except ImportError:
            self._pyrf24 = None
            self._pyrf24_available = False
            logger.warning("pyrf24 not installed - hardware mode unavailable")
    
    def is_available(self) -> bool:
        """Check if hardware backend is available (pyrf24 installed)."""
        return self._pyrf24_available
    
    def initialize(self) -> bool:
        """Initialize the nRF24L01+ radio for passive scanning.
        
        Returns:
            True if initialization successful
            
        Raises:
            RadioInitError: If radio initialization fails
            SPIError: If SPI communication fails
            RadioNotFoundError: If nRF24L01+ not detected
        """
        with self._lock:
            if not self._pyrf24_available:
                raise RadioInitError(
                    "pyrf24 library not available. Install with: pip install pyrf24"
                )
            
            if not self._check_spi_device():
                raise SPIError(
                    f"SPI device /dev/spidev0.{self._hw_config.csn_pin} not found. "
                    "Enable SPI with: sudo raspi-config -> Interface Options -> SPI"
                )
            
            try:
                self._radio = self._pyrf24.RF24(
                    self._hw_config.ce_pin,
                    self._hw_config.csn_pin
                )
                
                if not self._radio.begin():
                    raise RadioNotFoundError(
                        "nRF24L01+ not responding. Check wiring:\n"
                        f"  CE=GPIO{self._hw_config.ce_pin} (Pin 22)\n"
                        f"  CSN=GPIO8 (SPI CE0, Pin 24)\n"
                        "  SCK=GPIO11 (Pin 23)\n"
                        "  MOSI=GPIO10 (Pin 19)\n"
                        "  MISO=GPIO9 (Pin 21)\n"
                        "  3.3V (Pin 1 or 17)\n"
                        "  GND (Pin 6, 9, 14, 20, 25, 30, 34, 39)"
                    )
                
                self._radio.setPALevel(self._pyrf24.RF24_PA_LOW)
                self._radio.setDataRate(self._pyrf24.RF24_1MBPS)
                self._radio.setCRCLength(self._pyrf24.RF24_CRC_16)
                self._radio.setAutoAck(False)
                self._radio.stopListening()
                self._radio.setRetries(0, 0)
                
                self._current_channel = self._channel_config.start_channel
                self._radio.setChannel(self._current_channel)
                
                self._initialized = True
                logger.info(f"nRF24L01+ initialized on channel {self._current_channel}")
                return True
                
            except Exception as e:
                self._initialized = False
                self._radio = None
                if "SPI" in str(type(e)).upper() or "spi" in str(e).lower():
                    raise SPIError(f"SPI initialization failed: {e}") from e
                raise RadioInitError(f"Failed to initialize radio: {e}") from e
    
    def _check_spi_device(self) -> bool:
        """Check if SPI device exists."""
        spi_path = f"/dev/spidev0.{self._hw_config.csn_pin}"
        return os.path.exists(spi_path)
    
    def is_initialized(self) -> bool:
        return self._initialized
    
    def set_channel(self, channel: int) -> None:
        """Set the radio channel.
        
        Args:
            channel: Channel number (0-125)
            
        Raises:
            InvalidChannelError: If channel out of range
            HardwareError: If radio not initialized
        """
        with self._lock:
            if not self._initialized:
                raise HardwareError("Radio not initialized")
            if not (0 <= channel <= 125):
                raise InvalidChannelError(channel)
            
            self._current_channel = channel
            self._radio.setChannel(channel)
            time.sleep(0.00013)
    
    def get_channel(self) -> int:
        """Get the current channel."""
        with self._lock:
            return self._current_channel
    
    def read_rpd(self) -> bool:
        """Read RPD (Received Power Detector) status.
        
        Returns:
            True if signal detected above threshold
            
        Raises:
            HardwareError: If radio not initialized or read fails
        """
        with self._lock:
            if not self._initialized:
                raise HardwareError("Radio not initialized")
            
            try:
                return bool(self._radio.testRPD())
            except Exception as e:
                raise HardwareError(f"RPD read failed: {e}") from e
    
    def scan_channel(
        self,
        channel: int,
        duration: Optional[float] = None,
        interval: Optional[float] = None,
    ) -> Tuple[int, int, int]:
        """Scan a channel for RPD activity.
        
        Args:
            channel: Channel to scan
            duration: Measurement window (seconds)
            interval: Sampling interval (seconds)
            
        Returns:
            Tuple of (valid_samples, rpd_positive, rpd_negative)
        """
        with self._lock:
            if not self._initialized:
                raise HardwareError("Radio not initialized")
            
            duration = self._scan_config.measurement_window if duration is None else duration
            interval = self._scan_config.sampling_interval if interval is None else interval
            
            self.set_channel(channel)
            samples = int(duration / interval)
            valid = 0
            positive = 0
            negative = 0
            
            start_time = time.monotonic()
            for i in range(samples):
                try:
                    rpd = self.read_rpd()
                    valid += 1
                    if rpd:
                        positive += 1
                    else:
                        negative += 1
                except HardwareError:
                    pass
                
                elapsed = time.monotonic() - start_time
                expected = (i + 1) * interval
                sleep_time = expected - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            return valid, positive, negative
    
    def cleanup(self) -> None:
        """Clean up radio resources."""
        with self._lock:
            if self._radio and self._initialized:
                try:
                    self._radio.powerDown()
                except Exception as e:
                    logger.warning(f"Error during radio cleanup: {e}")
            self._initialized = False
            self._radio = None
    
    def get_info(self) -> Dict[str, Any]:
        """Get radio information for diagnostics."""
        with self._lock:
            if not self._initialized:
                return {"initialized": False}
            
            try:
                return {
                    "initialized": True,
                    "channel": self._current_channel,
                    "pa_level": self._radio.getPALevel(),
                    "data_rate": self._radio.getDataRate(),
                    "crc_length": self._radio.getCRCLength(),
                    "is_pv": self._radio.isPVariant(),
                    "ce_pin": self._hw_config.ce_pin,
                    "csn_pin": self._hw_config.csn_pin,
                    "spi_speed": self._hw_config.spi_speed,
                }
            except Exception as e:
                return {"initialized": True, "error": str(e)}
    
    @contextmanager
    def locked(self):
        """Context manager for exclusive radio access."""
        self._lock.acquire()
        try:
            yield self
        finally:
            self._lock.release()


def check_hardware_availability() -> Dict[str, Any]:
    """Check hardware availability without initializing radio.
    
    Returns:
        Dictionary with availability information
    """
    result = {
        "pyrf24_installed": False,
        "pyrf24_version": None,
        "spi_devices": [],
        "gpio_access": False,
        "errors": [],
        "platform": "unknown",
    }
    
    try:
        import platform
        result["platform"] = platform.platform()
    except Exception:
        pass
    
    try:
        import pyrf24
        result["pyrf24_installed"] = True
        result["pyrf24_version"] = getattr(pyrf24, "__version__", "unknown")
    except ImportError as e:
        result["errors"].append(f"pyrf24 not installed: {e}")
    
    try:
        for bus in range(2):
            for device in range(2):
                path = f"/dev/spidev{bus}.{device}"
                if os.path.exists(path):
                    result["spi_devices"].append(path)
    except Exception as e:
        result["errors"].append(f"SPI check failed: {e}")
    
    try:
        result["gpio_access"] = os.access("/dev/gpiomem", os.R_OK | os.W_OK)
    except Exception:
        pass
    
    return result


def run_hardware_diagnostic() -> Tuple[bool, str]:
    """Run full hardware diagnostic.
    
    Returns:
        Tuple of (success, message)
    """
    result = check_hardware_availability()
    
    if not result["pyrf24_installed"]:
        return False, "pyrf24 not installed"
    
    if not result["spi_devices"]:
        return False, "No SPI devices found. Enable SPI in raspi-config"
    
    if not result["gpio_access"]:
        return False, "No GPIO access. Check user is in gpio group"
    
    try:
        config = ChannelConfig()
        scan_config = ScanConfig()
        hw_config = HardwareConfig()
        radio = HardwareRadio(config, scan_config, hw_config)
        radio.initialize()
        info = radio.get_info()
        radio.cleanup()
        return True, f"Hardware OK: {info}"
    except Exception as e:
        return False, f"Hardware test failed: {e}"