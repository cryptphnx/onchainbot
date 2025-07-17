"""
Prometheus metrics exporter for mirror trading bot.

Defines counters, histograms, and gauges for monitoring.
Call init_metrics() to start the HTTP metrics server on port 8000.
"""
import time

from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Metric definitions
EVENT_COUNTER = Counter(
    'mirrorbot_events_total',
    'Total number of mirrorbot events processed',
    ['event_type'],
)
LATENCY_HISTOGRAM = Histogram(
    'mirrorbot_trade_latency_seconds',
    'Latency of mirror trade execution in seconds',
)
SLIPPAGE_GAUGE = Gauge(
    'mirrorbot_slippage_bps',
    'Current slippage in basis points',
)


def init_metrics(port: int = 8000) -> None:
    """
    Start the Prometheus HTTP server to expose metrics.

    Args:
        port: TCP port where metrics are served (default: 8000).
    """
    start_http_server(port)


def observe_event(event_type: str) -> None:
    """
    Increment the event counter for a given event type.
    """
    EVENT_COUNTER.labels(event_type=event_type).inc()


def observe_latency(latency_seconds: float) -> None:
    """
    Record a latency observation for trade execution.
    """
    LATENCY_HISTOGRAM.observe(latency_seconds)


def set_slippage_bps(bps: float) -> None:
    """
    Update the slippage gauge to the latest basis points value.
    """
    SLIPPAGE_GAUGE.set(bps)


def track_trade(event_type: str, start_time: float, slippage_bps: float) -> None:
    """
    Helper to record an event, its latency since start_time, and slippage gauge.

    Args:
        event_type: identifier for the type of trade event.
        start_time: timestamp when trade started (time.time()).
        slippage_bps: slippage in basis points to record.
    """
    observe_event(event_type)
    observe_latency(time.time() - start_time)
    set_slippage_bps(slippage_bps)
