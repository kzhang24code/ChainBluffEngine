# ChainBluff Engine

## Overview
ChainBluff is a poker simulation and strategy engine that integrates:
- **Commit-Reveal** cryptographic fairness protocol for provably fair card dealing
- **Counterfactual Regret Minimization (CFR)** AI agent for Nash Equilibrium strategies
- **Blockchain Integration** via web3.py for Ethereum smart contract interaction

## Project Architecture

```
chainbluff/
├── app.py                 # Flask entry point with SocketIO events
├── src/
│   ├── __init__.py
│   ├── models.py          # SQLAlchemy models (GameState, HandHistory, RegretTable)
│   ├── poker_engine.py    # Card deck, hand evaluator, game logic
│   ├── cfr_strategy.py    # CFR AI agent for GTO strategies
│   └── blockchain_bridge.py # Web3.py integration for smart contracts
├── templates/
│   └── index.html         # Single-page application UI
├── static/                # Static assets
└── chainbluff.db          # SQLite database
```

## Key Components

### Poker Engine (poker_engine.py)
- 52-card deck with Commit-Reveal scheme
- Server generates `server_seed`, user provides `client_seed`
- Deck order determined by `hash(server_seed + client_seed)`
- Hand evaluator ranks 7-card hands (Texas Hold'em style)

### CFR Strategy (cfr_strategy.py)
- Counterfactual Regret Minimization algorithm
- Maintains regret_sum and strategy_sum for information sets
- Self-training capability to learn Nash Equilibrium strategies
- Provides GTO (Game Theory Optimal) advice with Expected Value calculations

### Blockchain Bridge (blockchain_bridge.py)
- Web3.py integration for Ethereum-compatible contracts
- Manages wallet private keys via environment variables
- Functions: deploy_contract, create_game, commit_hand, reveal_and_payout

### Flask App (app.py)
- SocketIO events: join_table, bet_action, showdown, get_gto_advice
- Real-time game state updates
- AI opponent using CFR agent

## Running the Application
```bash
python app.py
```
The server runs on port 5000 with Flask-SocketIO using eventlet.

## Environment Variables
- `SECRET_KEY`: Flask session secret
- `ETH_PROVIDER_URL`: Ethereum RPC endpoint (optional)
- `ETH_PRIVATE_KEY`: Ethereum wallet private key (optional)
- `POKER_CONTRACT_ADDRESS`: Deployed contract address (optional)

## Database
Uses SQLite with SQLAlchemy ORM. Tables:
- `regret_table`: Stores CFR AI learned strategies
- `game_states`: Active game sessions
- `hand_history`: Completed hands for provability

## Commit-Reveal Protocol Flow
1. When user creates a game or requests a new hand, server generates commitment (hash of server seed)
2. Server emits `commitment_ready` event with the commitment
3. User provides client seed after seeing the commitment
4. Server reveals server seed and shuffles deck using `hash(server_seed + client_seed)`
5. At showdown, fairness proof is provided for verification

## GTO Advisor
The GTO panel shows:
- Hand Equity: Estimated win probability based on hole cards
- Expected Value (EV): Weighted expected return for each action
- Recommended Action: Best action based on CFR strategy
- Strategy Distribution: Probability weights for each action

## Recent Changes
- Initial project setup (January 2026)
- Implemented poker engine with Commit-Reveal fairness protocol
- Created CFR AI agent with proper game-tree traversal and regret matching
- Built blockchain bridge for Ethereum integration with commit/reveal/payout
- Developed single-page UI with Tailwind CSS and WebSocket integration
- Added hand equity estimation and GTO advice panel
- Implemented event-driven commit-reveal flow on frontend
- Added Random Swap button to swap seats with AI
- Enhanced game log with color-coded entries, better scrolling, and improved visibility
- Added separate bet chip indicators on table before pot collection
- Fold now shows overlay on cards instead of popup alert
- Showdown results display in game log instead of popup
