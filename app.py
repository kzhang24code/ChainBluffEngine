import os
import secrets
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from dotenv import load_dotenv

from src.models import init_db, get_session as get_db_session, GameState, HandHistory
from src.poker_engine import PokerGame, Card
from src.cfr_strategy import CFRAgent, create_info_set, estimate_hand_equity
from src.blockchain_bridge import BlockchainBridge

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

init_db()

games = {}
cfr_agent = CFRAgent(load_from_db=True)
blockchain = BlockchainBridge()


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health')
def health():
    return jsonify({
        'status': 'healthy',
        'blockchain_connected': blockchain.is_connected()
    })


@app.route('/api/train', methods=['POST'])
def train_ai():
    data = request.json or {}
    iterations = data.get('iterations', 1000)
    cfr_agent.train(iterations)
    return jsonify({'status': 'Training complete', 'iterations': iterations})


@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    emit('connected', {'sid': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")


@socketio.on('create_game')
def handle_create_game(data):
    player_name = data.get('name', 'Player')
    session_id = secrets.token_hex(16)
    
    game = PokerGame(session_id)
    game.add_player(request.sid, player_name, chips=1000)
    game.add_player('ai_player', 'AI Opponent', chips=1000)
    
    games[session_id] = game
    
    join_room(session_id)
    
    commitment = game.request_commitment()
    
    if blockchain.is_connected():
        try:
            blockchain.commit_hand(session_id, commitment)
        except Exception as e:
            print(f"Blockchain commit failed: {e}")
    
    emit('game_created', {
        'session_id': session_id,
        'message': f'Game created! Session: {session_id}',
        'commitment': commitment
    })


@socketio.on('join_table')
def handle_join_table(data):
    session_id = data.get('session_id')
    player_name = data.get('name', 'Player')
    
    if session_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = games[session_id]
    game.add_player(request.sid, player_name, chips=1000)
    
    join_room(session_id)
    
    emit('joined_table', game.get_state(), room=session_id)


@socketio.on('request_commitment')
def handle_request_commitment(data):
    session_id = data.get('session_id')
    
    if session_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = games[session_id]
    commitment = game.request_commitment()
    
    if blockchain.is_connected():
        try:
            blockchain.commit_hand(session_id, commitment)
        except Exception as e:
            print(f"Blockchain commit failed: {e}")
    
    emit('commitment_ready', {
        'session_id': session_id,
        'commitment': commitment,
        'message': 'Server committed. Please provide your client seed.'
    })


@socketio.on('start_hand')
def handle_start_hand(data):
    session_id = data.get('session_id')
    client_seed = data.get('client_seed', secrets.token_hex(16))
    
    if session_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = games[session_id]
    
    if not game.deck.is_committed:
        emit('error', {'message': 'Server must commit first. Request commitment.'})
        return
    
    state = game.start_hand(client_seed)
    
    for player in game.players:
        if player.id == request.sid:
            player_state = state.copy()
            player_state['your_cards'] = [c.to_dict() for c in player.hole_cards]
            emit('hand_started', player_state)
        elif player.id.startswith('ai_'):
            pass
    
    emit('game_state', state, room=session_id)


@socketio.on('bet_action')
def handle_bet_action(data):
    session_id = data.get('session_id')
    action = data.get('action')
    amount = data.get('amount', 0)
    
    if session_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = games[session_id]
    
    result = game.process_action(request.sid, action, amount)
    
    if 'error' in result:
        emit('error', result)
        return
    
    for player in game.players:
        if player.id == request.sid:
            player_state = result.copy()
            player_state['your_cards'] = [c.to_dict() for c in player.hole_cards]
            emit('action_result', player_state)
    
    emit('game_state', result, room=session_id)
    
    if game.stage == 'showdown':
        winner_result = game.determine_winner()
        emit('showdown', winner_result, room=session_id)
        
        _save_hand_history(game, winner_result)
    else:
        _process_ai_turn(session_id, game)


def _process_ai_turn(session_id: str, game: PokerGame):
    print(f"[AI TURN] Checking AI turn, current_player_index={game.current_player_index}, stage={game.stage}")
    
    ai_player = None
    for player in game.players:
        if player.id.startswith('ai_') and not player.is_folded:
            ai_player = player
            break
    
    if not ai_player:
        print("[AI TURN] No active AI player found")
        return
    
    current_player = game.players[game.current_player_index]
    print(f"[AI TURN] Current player: {current_player.id}, AI player: {ai_player.id}")
    
    if current_player.id != ai_player.id:
        print(f"[AI TURN] Not AI's turn, returning")
        return
    
    print(f"[AI TURN] AI is taking action!")
    
    info_set = create_info_set(
        ai_player.hole_cards,
        game.community_cards,
        '',
        game.pot,
        game.stage
    )
    
    available_actions = ['fold', 'call']
    if ai_player.current_bet >= game.current_bet:
        available_actions = ['fold', 'check', 'raise_small', 'raise_big']
    
    action, confidence = cfr_agent.get_action(info_set, available_actions)
    
    action_map = {
        'check': 'check',
        'call': 'call',
        'fold': 'fold',
        'raise_small': 'raise',
        'raise_big': 'raise',
        'raise_half': 'raise',
        'raise_pot': 'raise',
        'all_in': 'all_in'
    }
    
    amount = 0
    if action == 'raise_small':
        amount = game.pot * 0.5
    elif action == 'raise_big':
        amount = game.pot
    elif action == 'raise_half':
        amount = game.pot * 0.5
    elif action == 'raise_pot':
        amount = game.pot
    
    import time
    time.sleep(1)
    
    result = game.process_action(ai_player.id, action_map.get(action, 'call'), amount)
    
    socketio.emit('ai_action', {
        'action': action,
        'amount': amount,
        'confidence': confidence
    }, room=session_id)
    
    socketio.emit('game_state', result, room=session_id)
    
    if game.stage == 'showdown':
        winner_result = game.determine_winner()
        socketio.emit('showdown', winner_result, room=session_id)
        _save_hand_history(game, winner_result)


@socketio.on('get_gto_advice')
def handle_gto_advice(data):
    session_id = data.get('session_id')
    
    if session_id not in games:
        emit('error', {'message': 'Game not found'})
        return
    
    game = games[session_id]
    
    player = None
    for p in game.players:
        if p.id == request.sid:
            player = p
            break
    
    if not player:
        emit('error', {'message': 'Player not found'})
        return
    
    info_set = create_info_set(
        player.hole_cards,
        game.community_cards,
        '',
        game.pot,
        game.stage
    )
    
    hand_equity = estimate_hand_equity(
        player.hole_cards,
        game.community_cards,
        game.stage
    )
    
    ev_analysis = cfr_agent.calculate_ev(
        info_set,
        game.pot,
        game.current_bet - player.current_bet,
        player.chips,
        hand_equity
    )
    
    emit('gto_advice', ev_analysis)


def _save_hand_history(game: PokerGame, winner_result: dict):
    try:
        db_session = get_db_session()
        
        history = HandHistory(
            session_id=game.session_id,
            hand_number=1,
            player_cards={p.id: [c.to_dict() for c in p.hole_cards] for p in game.players},
            community_cards=[c.to_dict() for c in game.community_cards],
            actions=[],
            winner=winner_result['winner']['id'],
            pot_won=winner_result['pot'],
            hand_rank=winner_result['hand_rank'],
            server_seed=game.deck.server_seed,
            client_seed=game.deck.client_seed
        )
        
        db_session.add(history)
        db_session.commit()
        db_session.close()
        
        if blockchain.is_connected():
            try:
                winner_id = winner_result['winner']['id']
                winner_player = next((p for p in game.players if p.id == winner_id), None)
                winner_address = winner_player.wallet_address if winner_player and winner_player.wallet_address else None
                
                if winner_address and winner_address.startswith('0x') and len(winner_address) == 42:
                    blockchain.reveal_and_payout(
                        game.session_id,
                        winner_address,
                        game.deck.server_seed,
                        game.deck.client_seed
                    )
                else:
                    print(f"Skipping blockchain payout - no valid wallet address for winner")
            except Exception as e:
                print(f"Blockchain payout failed: {e}")
                
    except Exception as e:
        print(f"Error saving hand history: {e}")


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
