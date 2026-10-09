"""All tunable settings live here."""

# ---- Wiring (BCM numbering) -------------------------------------------------
CE_PIN = 25                 # GPIO25
CSN_PIN = 0                 # SPIDEV driver: 0 -> /dev/spidev0.0 (GPIO8 / CE0 is driven by the kernel)
SPI_SPEED_HZ = 10_000_000   # drop to 2_000_000 if you see SPI errors with long jumper wires

# ---- Radio ------------------------------------------------------------------
NUM_CHANNELS = 126          # channels 0..125  ->  2400..2525 MHz
BASE_MHZ = 2400
DEFAULT_DWELL_US = 200      # time spent listening on each channel before reading RPD
MIN_DWELL_US = 130          # nRF24 needs ~130 us to settle into RX

# ---- Display ----------------------------------------------------------------
UPDATE_MS = 250             # GUI refresh period (raise to 400 if the Pi struggles)
WINDOW_FRAMES = 8           # spectrum = average of the last N frames (~2 s at 250 ms)
WATERFALL_ROWS = 100        # waterfall history length (rows)
ACTIVITY_THRESHOLD = 0.05   # a channel is "active" if >= 5 % of recent sweeps had a hit
PEAK_DECAY = 0.99           # peak-hold fall-off per frame
