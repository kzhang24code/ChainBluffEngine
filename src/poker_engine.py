import hashlib
import secrets
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field
import json


RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS = ['h', 'd', 'c', 's']
RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}


@dataclass
class Card:
    rank: str
    suit: str
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __repr__(self):
        return str(self)
    
    def to_dict(self):
        return {'rank': self.rank, 'suit': self.suit}
    
    @staticmethod
    def from_dict(d):
        return Card(d['rank'], d['suit'])


@dataclass
class Player:
    id: str
    name: str
    chips: float = 1000.0
    hole_cards: List[Card] = field(default_factory=list)
    current_bet: float = 0.0
    is_folded: bool = False
    is_all_in: bool = False
    wallet_address: str = ""
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'chips': self.chips,
            'hole_cards': [c.to_dict() for c in self.hole_cards],
            'current_bet': self.current_bet,
            'is_folded': self.is_folded,
            'is_all_in': self.is_all_in,
            'wallet_address': self.wallet_address
        }


class CommitRevealDeck:
    def __init__(self):
        self.server_seed = None
        self.client_seed = None
        self.deck = []
        self.deck_index = 0
        self.commitment = None
        self.is_committed = False
        self.is_revealed = False
        
    def generate_commitment(self) -> str:
        self.server_seed = secrets.token_hex(32)
        self.commitment = hashlib.sha256(self.server_seed.encode()).hexdigest()
        self.is_committed = True
        self.is_revealed = False
        return self.commitment
    
    def get_commitment(self) -> str:
        if not self.is_committed:
            return self.generate_commitment()
        return self.commitment
    
    def reveal_and_shuffle(self, client_seed: str) -> bool:
        if not self.is_committed:
            raise ValueError("Must generate commitment before revealing")
        if self.is_revealed:
            raise ValueError("Already revealed for this hand")
        
        self.client_seed = client_seed
        combined = self.server_seed + client_seed
        seed_hash = hashlib.sha256(combined.encode()).digest()
        seed_int = int.from_bytes(seed_hash[:4], 'big')
        
        self.deck = [Card(r, s) for r in RANKS for s in SUITS]
        
        import random
        random.seed(seed_int)
        random.shuffle(self.deck)
        
        self.deck_index = 0
        self.is_revealed = True
        return True
    
    def verify_commitment(self, server_seed: str, claimed_commitment: str) -> bool:
        expected = hashlib.sha256(server_seed.encode()).hexdigest()
        return expected == claimed_commitment
    
    def reset(self):
        self.server_seed = None
        self.client_seed = None
        self.deck = []
        self.deck_index = 0
        self.commitment = None
        self.is_committed = False
        self.is_revealed = False
    
    def deal_card(self) -> Optional[Card]:
        if self.deck_index >= len(self.deck):
            return None
        card = self.deck[self.deck_index]
        self.deck_index += 1
        return card
    
    def deal_cards(self, count: int) -> List[Card]:
        cards = []
        for _ in range(count):
            card = self.deal_card()
            if card is not None:
                cards.append(card)
        return cards
    
    def verify_fairness(self) -> Dict:
        return {
            'server_seed': self.server_seed,
            'client_seed': self.client_seed,
            'commitment': self.commitment,
            'combined_hash': hashlib.sha256((self.server_seed + self.client_seed).encode()).hexdigest()
        }


class HandEvaluator:
    HAND_RANKS = {
        'high_card': 0,
        'pair': 1,
        'two_pair': 2,
        'three_of_a_kind': 3,
        'straight': 4,
        'flush': 5,
        'full_house': 6,
        'four_of_a_kind': 7,
        'straight_flush': 8,
        'royal_flush': 9
    }
    
    @staticmethod
    def evaluate_hand(cards: List[Card]) -> Tuple[int, str, List[int]]:
        if len(cards) < 5:
            return (0, 'high_card', [RANK_VALUES[cards[0].rank]] if cards else [0])
        
        best_hand = None
        best_rank = -1
        best_name = 'high_card'
        best_kickers = []
        
        from itertools import combinations
        for combo in combinations(cards, 5):
            hand_rank, hand_name, kickers = HandEvaluator._evaluate_five_cards(list(combo))
            if hand_rank > best_rank or (hand_rank == best_rank and kickers > best_kickers):
                best_rank = hand_rank
                best_name = hand_name
                best_kickers = kickers
        
        return (best_rank, best_name, best_kickers)
    
    @staticmethod
    def _evaluate_five_cards(cards: List[Card]) -> Tuple[int, str, List[int]]:
        ranks = sorted([RANK_VALUES[c.rank] for c in cards], reverse=True)
        suits = [c.suit for c in cards]
        
        is_flush = len(set(suits)) == 1
        is_straight = HandEvaluator._is_straight(ranks)
        
        if is_straight and ranks == [14, 5, 4, 3, 2]:
            ranks = [5, 4, 3, 2, 1]
        
        rank_counts = {}
        for r in ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        
        counts = sorted(rank_counts.values(), reverse=True)
        sorted_ranks = sorted(rank_counts.keys(), key=lambda x: (rank_counts[x], x), reverse=True)
        
        if is_straight and is_flush:
            if ranks[0] == 14 and ranks[1] == 13:
                return (9, 'royal_flush', ranks)
            return (8, 'straight_flush', ranks)
        
        if counts == [4, 1]:
            return (7, 'four_of_a_kind', sorted_ranks)
        
        if counts == [3, 2]:
            return (6, 'full_house', sorted_ranks)
        
        if is_flush:
            return (5, 'flush', ranks)
        
        if is_straight:
            return (4, 'straight', ranks)
        
        if counts == [3, 1, 1]:
            return (3, 'three_of_a_kind', sorted_ranks)
        
        if counts == [2, 2, 1]:
            return (2, 'two_pair', sorted_ranks)
        
        if counts == [2, 1, 1, 1]:
            return (1, 'pair', sorted_ranks)
        
        return (0, 'high_card', ranks)
    
    @staticmethod
    def _is_straight(ranks: List[int]) -> bool:
        unique = sorted(set(ranks), reverse=True)
        if len(unique) != 5:
            return False
        
        if unique[0] - unique[4] == 4:
            return True
        
        if unique == [14, 5, 4, 3, 2]:
            return True
        
        return False
    
    @staticmethod
    def compare_hands(hand1: List[Card], hand2: List[Card]) -> int:
        rank1, name1, kickers1 = HandEvaluator.evaluate_hand(hand1)
        rank2, name2, kickers2 = HandEvaluator.evaluate_hand(hand2)
        
        if rank1 != rank2:
            return 1 if rank1 > rank2 else -1
        
        for k1, k2 in zip(kickers1, kickers2):
            if k1 != k2:
                return 1 if k1 > k2 else -1
        
        return 0


class PokerGame:
    STAGES = ['preflop', 'flop', 'turn', 'river', 'showdown']
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.deck = CommitRevealDeck()
        self.players: List[Player] = []
        self.community_cards: List[Card] = []
        self.pot = 0.0
        self.current_bet = 0.0
        self.stage = 'preflop'
        self.current_player_index = 0
        self.dealer_index = 0
        self.small_blind = 5.0
        self.big_blind = 10.0
        self.actions_this_round = 0
        self.last_raise_amount = 0.0
        
    def add_player(self, player_id: str, name: str, chips: float = 1000.0) -> Player:
        player = Player(id=player_id, name=name, chips=chips)
        self.players.append(player)
        return player
    
    def request_commitment(self) -> str:
        self.deck.reset()
        return self.deck.generate_commitment()
    
    def start_hand(self, client_seed: str) -> Dict:
        if self.deck.is_revealed:
            self.deck.reset()
            self.deck.generate_commitment()
        
        if not self.deck.is_committed:
            self.deck.generate_commitment()
        
        self.deck.reveal_and_shuffle(client_seed)
        
        self.community_cards = []
        self.pot = 0.0
        self.current_bet = 0.0
        self.stage = 'preflop'
        self.actions_this_round = 0
        
        for player in self.players:
            player.hole_cards = []
            player.current_bet = 0.0
            player.is_folded = False
            player.is_all_in = False
        
        for player in self.players:
            player.hole_cards = self.deck.deal_cards(2)
        
        self._post_blinds()
        
        return self.get_state()
    
    def _post_blinds(self):
        if len(self.players) >= 2:
            sb_index = (self.dealer_index + 1) % len(self.players)
            bb_index = (self.dealer_index + 2) % len(self.players)
            
            self._make_bet(sb_index, self.small_blind)
            self._make_bet(bb_index, self.big_blind)
            
            self.current_bet = self.big_blind
            self.current_player_index = (bb_index + 1) % len(self.players)
    
    def _make_bet(self, player_index: int, amount: float):
        player = self.players[player_index]
        actual_bet = min(amount, player.chips)
        player.chips -= actual_bet
        player.current_bet += actual_bet
        self.pot += actual_bet
        if player.chips == 0:
            player.is_all_in = True
    
    def process_action(self, player_id: str, action: str, amount: float = 0) -> Dict:
        player = None
        player_index = -1
        for i, p in enumerate(self.players):
            if p.id == player_id:
                player = p
                player_index = i
                break
        
        if not player or player.is_folded:
            return {'error': 'Invalid player or already folded'}
        
        if action == 'fold':
            player.is_folded = True
        
        elif action == 'check':
            if player.current_bet < self.current_bet:
                return {'error': 'Cannot check, must call or raise'}
        
        elif action == 'call':
            call_amount = self.current_bet - player.current_bet
            self._make_bet(player_index, call_amount)
        
        elif action == 'raise':
            call_amount = self.current_bet - player.current_bet
            total_bet = call_amount + amount
            self._make_bet(player_index, total_bet)
            self.current_bet = player.current_bet
            self.last_raise_amount = amount
        
        elif action == 'all_in':
            self._make_bet(player_index, player.chips)
            if player.current_bet > self.current_bet:
                self.current_bet = player.current_bet
        
        self.actions_this_round += 1
        self._move_to_next_player()
        self._advance_game()
        
        return self.get_state()
    
    def _move_to_next_player(self):
        for _ in range(len(self.players)):
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            next_player = self.players[self.current_player_index]
            if not next_player.is_folded and not next_player.is_all_in:
                return
        self.current_player_index = 0
    
    def _advance_game(self):
        active_players = [p for p in self.players if not p.is_folded]
        
        if len(active_players) == 1:
            self.stage = 'showdown'
            return
        
        betting_complete = all(
            p.current_bet == self.current_bet or p.is_all_in or p.is_folded
            for p in self.players
        ) and self.actions_this_round >= len([p for p in self.players if not p.is_folded])
        
        if betting_complete:
            self._next_stage()
    
    def _reset_action_to_first_player(self):
        for i, player in enumerate(self.players):
            if not player.is_folded and not player.is_all_in:
                self.current_player_index = i
                return
        self.current_player_index = 0
    
    def _next_stage(self):
        stage_index = self.STAGES.index(self.stage)
        if stage_index < len(self.STAGES) - 1:
            self.stage = self.STAGES[stage_index + 1]
            
            for player in self.players:
                player.current_bet = 0
            self.current_bet = 0
            self.actions_this_round = 0
            
            if self.stage == 'flop':
                self.community_cards.extend(self.deck.deal_cards(3))
            elif self.stage == 'turn':
                self.community_cards.extend(self.deck.deal_cards(1))
            elif self.stage == 'river':
                self.community_cards.extend(self.deck.deal_cards(1))
            elif self.stage == 'showdown':
                pass
            
            if self.stage != 'showdown':
                self._reset_action_to_first_player()
    
    def determine_winner(self) -> Dict:
        active_players = [p for p in self.players if not p.is_folded]
        
        if len(active_players) == 0:
            return {
                'winner': {'id': None, 'name': 'No winner'},
                'hand_rank': 'no active players',
                'pot': self.pot
            }
        
        if len(active_players) == 1:
            winner = active_players[0]
            winner.chips += self.pot
            return {
                'winner': winner.to_dict(),
                'hand_rank': 'opponent folded',
                'pot': self.pot
            }
        
        best_player = None
        best_rank = -1
        best_name = ''
        best_kickers = []
        
        for player in active_players:
            all_cards = player.hole_cards + self.community_cards
            rank, name, kickers = HandEvaluator.evaluate_hand(all_cards)
            
            if rank > best_rank or (rank == best_rank and kickers > best_kickers):
                best_player = player
                best_rank = rank
                best_name = name
                best_kickers = kickers
        
        if best_player is None:
            best_player = active_players[0]
            best_name = 'high card'
        
        best_player.chips += self.pot
        
        return {
            'winner': best_player.to_dict(),
            'hand_rank': best_name,
            'pot': self.pot,
            'fairness_proof': self.deck.verify_fairness()
        }
    
    def get_state(self) -> Dict:
        return {
            'session_id': self.session_id,
            'stage': self.stage,
            'pot': self.pot,
            'current_bet': self.current_bet,
            'community_cards': [c.to_dict() for c in self.community_cards],
            'players': [p.to_dict() for p in self.players],
            'current_player_index': self.current_player_index,
            'commitment': self.deck.commitment
        }
