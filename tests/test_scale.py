# ------------------------------------------------------------------ y-scale
def test_nice_round_up():
    from rf_spectrum_visualizer.gui.theme import nice_round_up, MIN_SCALE_MAX
    assert MIN_SCALE_MAX == 25.0
    assert nice_round_up(3.0) == 25.0   # floor at 25
    assert nice_round_up(25.0) == 25.0
    assert nice_round_up(26.0) == 50.0
    assert nice_round_up(30.0) == 50.0
    assert nice_round_up(50.0) == 50.0
    assert nice_round_up(60.0) == 100.0
    assert nice_round_up(150.0) == 100.0


def test_y_scale_manager_auto():
    from rf_spectrum_visualizer.gui.theme import YScaleManager
    m = YScaleManager()
    assert m.mode == "auto"
    assert m.label() == "Activity % (scale 0-25)"
    # Grow immediately (multiplier 1.15, min scale 25)
    assert m.compute(8.0) == 25.0   # 8*1.15=9.2 -> max(25,9.2)=25 -> nice 25
    assert m.compute(16.0) == 25.0  # 16*1.15=18.4 -> max(25,18.4)=25 -> nice 25
    assert m.compute(24.0) == 50.0  # 24*1.15=27.6 -> max(25,27.6)=27.6 -> nice 50
    assert m.label() == "Activity % (scale 0-50)"
    # Shrink slowly: hysteresis (shrink threshold = current * 0.7)
    m2 = YScaleManager()
    m2.compute(80.0)  # 80*1.15=92 -> nice 100
    assert m2.compute(55.0) == 100.0  # 55*1.15=63.25 -> nice 100, keep 100 (100 not < 70)
    assert m2.compute(40.0) == 50.0   # 40*1.15=46 -> nice 50, 50 < 70, shrink to 50


def test_y_scale_manager_fixed():
    from rf_spectrum_visualizer.gui.theme import YScaleManager
    m = YScaleManager()
    m.set_mode("fixed")
    assert m.compute(5.0) == 100.0
    assert m.label() == "Activity % (scale 0-100)"
    m.set_mode("auto")
    assert m.compute(3.0) == 25.0  # back to auto, floor at 25


def test_waterfall_cmap_constant():
    from rf_spectrum_visualizer.gui.theme import WATERFALL_CMAP
    assert WATERFALL_CMAP == "RdYlGn_r"


# ------------------------------------------------------------------ ScanState state machine
def test_scan_state_start_stop_start():
    from rf_spectrum_visualizer.scan_worker import ScanState
    c = ScanState()
    assert c.start_enabled
    assert not c.stop_enabled
    assert c.start() is True
    assert not c.start_enabled
    assert not c.stop_enabled  # STARTING: stop not yet enabled
    c.started()
    assert c.state == ScanState.RUNNING
    assert c.stop_enabled
    c.stop()
    assert c.state == ScanState.STOPPING
    assert not c.start_enabled
    assert not c.stop_enabled
    c.stopped()
    assert c.start_enabled
    assert not c.stop_enabled
    assert c.start() is True  # can start again after stop


def test_scan_state_start_complete_start():
    from rf_spectrum_visualizer.scan_worker import ScanState
    c = ScanState()
    assert c.start() is True
    c.started()
    assert not c.start_enabled
    c.complete()
    assert c.start_enabled
    assert c.start() is True


def test_scan_state_start_error_start():
    from rf_spectrum_visualizer.scan_worker import ScanState
    c = ScanState()
    assert c.start() is True
    c.started()
    assert not c.start_enabled
    c.error()
    assert c.start_enabled
    assert c.start() is True


def test_scan_state_rapid_start_stop():
    from rf_spectrum_visualizer.scan_worker import ScanState
    c = ScanState()
    for _ in range(10):
        assert c.start() is True
        c.started()
        assert not c.start_enabled
        assert c.stop_enabled
        c.stop()
        c.stopped()
        assert c.start_enabled


def test_scan_state_double_start_blocked():
    from rf_spectrum_visualizer.scan_worker import ScanState
    c = ScanState()
    assert c.start() is True
    assert c.start() is False  # already starting, blocked


# ------------------------------------------------------------------ Wi-Fi overlay
class _FakeSpan:
    def __init__(self):
        self.removed = False

    def remove(self):
        self.removed = True


class _FakeText:
    def __init__(self, t):
        self._text = t
        self.removed = False

    def get_text(self):
        return self._text

    def remove(self):
        self.removed = True


class _FakeAx:
    def __init__(self):
        self.spans = []
        self._wifi_spans = []
        self.texts = []
        self.ax_bar = self

    def axvspan(self, start, end, **kwargs):
        s = _FakeSpan()
        self.spans.append(s)
        return s

    def text(self, x, y, text, **kwargs):
        self.texts.append(_FakeText(text))

    def get_xaxis_transform(self):
        return "identity"


def test_wifi_bands_drawing():
    """_draw_wifi_bands should create 3 spans with correct nRF channel ranges."""
    from rf_spectrum_visualizer.gui.pages.live_spectrum import LiveSpectrumPage

    ax = _FakeAx()
    LiveSpectrumPage._draw_wifi_bands(ax, ax)
    assert len(ax.spans) == 3
    # Wi-Fi ch 1: nRF ~2-22 -> axvspan(1.5, 22.5)
    assert ax.spans[0] is not None
    # Wi-Fi ch 6: nRF ~27-47 -> axvspan(26.5, 47.5)
    assert ax.spans[1] is not None
    # Wi-Fi ch 11: nRF ~52-72 -> axvspan(51.5, 72.5)
    assert ax.spans[2] is not None
    # Labels present
    assert any("Wi-Fi ch 1" in t.get_text() for t in ax.texts)
    assert any("Wi-Fi ch 6" in t.get_text() for t in ax.texts)
    assert any("Wi-Fi ch 11" in t.get_text() for t in ax.texts)


def test_wifi_bands_remove():
    """_remove_wifi_bands should remove all spans and Wi-Fi text labels."""
    from rf_spectrum_visualizer.gui.pages.live_spectrum import LiveSpectrumPage

    ax = _FakeAx()
    LiveSpectrumPage._draw_wifi_bands(ax, ax)
    assert len(ax.spans) == 3
    assert len(ax._wifi_spans) == 3

    LiveSpectrumPage._remove_wifi_bands(ax)
    assert all(s.removed for s in ax.spans)
    assert ax._wifi_spans == []
    # Wi-Fi labels should be marked removed
    wifi_texts = [t for t in ax.texts if "Wi-Fi ch" in t.get_text()]
    assert all(t.removed for t in wifi_texts)
    # Non-Wi-Fi labels should remain
    non_wifi = [t.get_text() for t in ax.texts if not t.removed]
    assert len(non_wifi) == 0  # All texts added by _draw_wifi_bands are Wi-Fi labels


# ------------------------------------------------------------------ Waterfall newest-first (A13)
def test_waterfall_newest_first():
    """Waterfall _add_waterfall_row must put newest pass at row 0 (top).

    With origin='upper', row 0 is displayed at top. The fix shifts existing
    rows down by one and writes the new pass into row 0, so newest is always
    at top.
    """
    import numpy as np
    from rf_spectrum_visualizer.gui.pages.live_spectrum import (
        LiveSpectrumPage, WATERFALL_MAX_ROWS, WATERFALL_COLS
    )
    from rf_spectrum_visualizer.scan_backend import ChannelStats

    class MockPage:
        _waterfall_data = None
        _waterfill_row = 0

    page = MockPage()

    # Feed passes 1..5 (each pass has unique activity at channel 100)
    for pass_num in range(1, 6):
        stats = {
            100: ChannelStats(
                channel=100, freq_mhz=2500.0, samples=1,
                rpd_true=pass_num, activity_percent=float(pass_num)
            )
        }
        LiveSpectrumPage._add_waterfall_row(page, stats)

    # With fix: newest (pass 5) at row 0 (top), oldest (pass 1) at bottom
    assert page._waterfall_data[0, 100] == 5.0, (
        f"Expected newest (5.0) at row 0, got {page._waterfall_data[0, 100]}"
    )
    assert page._waterfall_data[4, 100] == 1.0, (
        f"Expected oldest (1.0) at row 4, got {page._waterfall_data[4, 100]}"
    )


def test_waterfall_wrap_around():
    """Waterfall wrap-around: more passes than WATERFALL_MAX_ROWS."""
    import numpy as np
    from rf_spectrum_visualizer.gui.pages.live_spectrum import (
        LiveSpectrumPage, WATERFALL_MAX_ROWS, WATERFALL_COLS
    )
    from rf_spectrum_visualizer.scan_backend import ChannelStats

    class MockPage:
        _waterfall_data = None
        _waterfill_row = 0

    page = MockPage()

    # Feed WATERFALL_MAX_ROWS + 3 passes
    for pass_num in range(1, WATERFALL_MAX_ROWS + 4):
        stats = {
            100: ChannelStats(
                channel=100, freq_mhz=2500.0, samples=1,
                rpd_true=pass_num, activity_percent=float(pass_num)
            )
        }
        LiveSpectrumPage._add_waterfall_row(page, stats)

    # After wrap-around, row 0 should have the most recent pass
    # (WATERFALL_MAX_ROWS + 3)
    expected_newest = WATERFALL_MAX_ROWS + 3
    assert page._waterfill_row == WATERFALL_MAX_ROWS + 3
    assert page._waterfall_data[0, 100] == float(expected_newest), (
        f"Expected newest ({expected_newest}) at row 0, "
        f"got {page._waterfall_data[0, 100]}"
    )
    # Row 1 should have pass WATERFALL_MAX_ROWS + 2
    assert page._waterfall_data[1, 100] == float(WATERFALL_MAX_ROWS + 2)