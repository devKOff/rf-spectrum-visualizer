"""RF Spectrum Visualizer - Main entry point."""

import sys
import logging
import argparse

from config import AppConfig, DEFAULT_CONFIG
from ui.main_window import MainWindow
from logging_config import setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="RF Spectrum Visualizer - 2.4 GHz ISM Band Monitor for nRF24L01+"
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Use simulation backend (default)"
    )
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="Use hardware backend (requires pyrf24 and Raspberry Pi)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration JSON file"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="RF Spectrum Visualizer 1.0.0"
    )
    return parser.parse_args()


def main() -> int:
    """Main application entry point."""
    args = parse_args()
    
    # Load configuration
    if args.config:
        from services.persistence_service import PersistenceService
        persistence = PersistenceService(args.config)
        config = persistence.config
    else:
        config = DEFAULT_CONFIG
    
    # Override backend from command line
    if args.hardware:
        config.default_backend = "hardware"
    elif args.sim:
        config.default_backend = "sim"
    
    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)
    
    logger = logging.getLogger("rf_visualizer.main")
    logger.info("Starting RF Spectrum Visualizer")
    logger.info(f"Backend: {config.default_backend}")
    logger.info(f"Channel range: {config.channel.start_channel}-{config.channel.end_channel}")
    
    try:
        app = MainWindow(config)
        app.run()
        return 0
    except Exception as e:
        logger.exception("Application error")
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())