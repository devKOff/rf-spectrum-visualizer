import time
from pyrf24 import RF24, RF24_1MBPS


class NRF24SpectrumScanner:
    """
    Receive-only nRF24L01 RF activity scanner.

    Frequency:
        2400 MHz to 2525 MHz

    Channel:
        0 to 125

    Measurement:
        RPD activity detection

    IMPORTANT:
        RPD is a threshold detector, not calibrated RSSI.
    """

    NUM_CHANNELS = 126
    START_FREQUENCY_MHZ = 2400

    def __init__(
        self,
        ce_pin=25,
        csn_pin=8,
        samples_per_channel=5,
        dwell_time=0.001
    ):
        self.ce_pin = ce_pin
        self.csn_pin = csn_pin

        self.samples_per_channel = samples_per_channel
        self.dwell_time = dwell_time

        self.radio = RF24(
            ce_pin,
            csn_pin
        )

        self.running = False

    def initialize(self):
        """Initialize and configure the nRF24L01."""

        if not self.radio.begin():
            raise RuntimeError(
                "nRF24L01 was not detected. "
                "Check SPI, CE, CSN and power connections."
            )

        # Scanner is receive-only.
        self.radio.set_auto_ack(False)

        # Disable CRC because we are not trying to decode packets.
        self.radio.crc_length = 0

        # Use 1 Mbps as a stable general-purpose radio configuration.
        self.radio.data_rate = RF24_1MBPS

        # Dummy RX address.
        #
        # The address is not used for identifying devices.
        # It simply gives the radio an RX pipe so that
        # start_listening() can place the chip in RX mode.
        self.radio.open_rx_pipe(
            1,
            b"SCAN1"
        )

        self.radio.flush_rx()

        # Put radio into a known state.
        self.radio.start_listening()
        time.sleep(0.0002)
        self.radio.stop_listening()

    def scan_channel(self, channel):
        """
        Scan one nRF24 channel.

        Returns:
            integer number of RPD detections.
        """

        if not 0 <= channel <= 125:
            raise ValueError(
                "Channel must be between 0 and 125."
            )

        detections = 0

        self.radio.channel = channel

        for _ in range(self.samples_per_channel):

            # Enter RX mode.
            self.radio.start_listening()

            # Allow the receiver to settle.
            time.sleep(self.dwell_time)

            # RPD is True when RF energy above the
            # nRF24 RPD threshold was detected.
            if self.radio.rpd:
                detections += 1

            self.radio.stop_listening()

            # Remove anything accidentally received.
            self.radio.flush_rx()

        return detections

    def scan(self):
        """
        Perform one complete 126-channel sweep.

        Returns:
            list of activity values from 0.0 to 1.0
        """

        results = []

        for channel in range(self.NUM_CHANNELS):

            detections = self.scan_channel(channel)

            activity = (
                detections /
                self.samples_per_channel
            )

            results.append(activity)

        return results

    @staticmethod
    def channel_to_frequency(channel):
        """Convert nRF24 channel to MHz."""

        return 2400 + channel

    def stop(self):
        """Stop scanning."""

        self.running = False

        try:
            self.radio.stop_listening()
            self.radio.flush_rx()
        except Exception:
            pass