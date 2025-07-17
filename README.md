# onchainbot

A mirror trading bot for Ethereum and Solana DeFi protocols.

## Features

- **Ingestion**: Capture pending swap events from Uniswap/1inch on Ethereum and swap notifications from Helius & Jito on Solana.
- **Execution**: Automatically mirror swap events via Flashbots bundles (ETH) and Jito bundles (SOL).
- **Risk Management**: Automatic position exit based on drawdown thresholds and time-to-live (TTL).
- **Alerts**: Send notifications to an n8n workflow via webhook.
- **Metrics**: Expose Prometheus metrics for events, latency, and slippage.

## Directory Structure

```
.    
├── core/               # Core utilities: positions, risk rules, alerts, metrics
├── ingestion/          # Swap event ingestion modules for ETH and SOL
├── exec/               # Execution modules for mirroring trades on ETH and SOL
├── src/onchainbot/     # Optional packaged CLI or integrations
├── tests/              # Unit tests
├── wallets_eth.json    # Sample Ethereum wallet configuration file
├── wallets_sol.json    # Sample Solana wallet configuration file
├── requirements.txt    # Python dependencies
├── pytest.ini          # Pytest configuration
└── README.md           # Project overview and usage
```

## Installation

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Configuration

Environment variables are used to configure endpoints and credentials:

### Ingestion
- `ALCHEMY_WS_URL`  : WebSocket URL for Ethereum pending tx ingestion (Alchemy).
- `HELIUS_WS_URL`   : WebSocket URL for Solana Helius enhanced events.
- `JITO_SHRED_URL`  : WebSocket URL for Solana Jito shardstream.
- `ETH_WALLETS_FILE`      : Path to `wallets_eth.json` with wallet list for ETH (default `wallets_eth.json`).
- `SOL_WALLETS_FILE`      : Path to `wallets_sol.json` with wallet list for SOL (default `wallets_sol.json`).

### Execution
- `ETH_RPC_URL`          : JSON-RPC URL for Ethereum node.
- `OX_API`               : 0x API key for swap quotes.
- `FLASHBOTS_SIGNER_KEY` : Private key for Flashbots signing.
- `FLASHBOTS_RELAY_URL`  : Flashbots relay endpoint (default `https://relay.flashbots.net`).
- `SOLANA_PRIVATE_KEY_JSON` or `SOLANA_KEYPAIR_PATH` : Keypair for Solana transactions.
- `JITO_BUNDLE_URL`      : HTTP endpoint for Jito bundle submission.

### Alerts & Risk
- `N8N_WEBHOOK_URL` : URL of the n8n webhook for alerts.
- `MIRROR_RATIO`    : Fraction of original trade size to mirror (default `0.02`).
- `TTL_SECONDS`     : Time-to-live for open positions in seconds (default `86400`).

## Metrics

The bot exposes Prometheus metrics on port 8000 by calling:

```python
from core.metrics import init_metrics

init_metrics(port=8000)
```

Available metrics:

- `mirrorbot_events_total{event_type}` (Counter)
- `mirrorbot_trade_latency_seconds`     (Histogram)
- `mirrorbot_slippage_bps`              (Gauge)

## Usage

Typical usage involves starting ingestion and execution coroutines under an `asyncio` event loop,
optionally integrating risk checks, alerts, and metrics updates:

```python
import asyncio
from core.metrics import init_metrics, track_trade
from core.alerts import notify
from core.risk import should_exit
from ingestion.eth import subscribe_pending
from exec.eth import mirror_buy, mirror_sell

async def main():
    init_metrics()
    # ... load wallets, subscribe to events, track trades, evaluate risk, send alerts ...

asyncio.run(main())
```

## Testing

Run the full test suite with:

```bash
pytest -q
```
