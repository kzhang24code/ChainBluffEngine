import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
from src.models import get_session, RegretTable


@dataclass
class InfoSet:
    hole_cards: str
    community_cards: str
    betting_history: str
    pot_size: float
    
    def __str__(self):
        return f"{self.hole_cards}|{self.community_cards}|{self.betting_history}|{int(self.pot_size)}"
    
    def to_key(self) -> str:
        return str(self)


class CFRAgent:
    ACTIONS = ['fold', 'check', 'call', 'raise_small', 'raise_big', 'all_in']
    
    def __init__(self, load_from_db: bool = True):
        self.regret_sum: Dict[str, np.ndarray] = {}
        self.strategy_sum: Dict[str, np.ndarray] = {}
        self.num_actions = len(self.ACTIONS)
        
        if load_from_db:
            self._load_from_db()
    
    def _load_from_db(self):
        try:
            session = get_session()
            entries = session.query(RegretTable).all()
            for entry in entries:
                info_set = entry.info_set
                self.regret_sum[info_set] = np.array(entry.regrets)
                self.strategy_sum[info_set] = np.array(entry.strategy_sum)
            session.close()
        except Exception as e:
            print(f"Could not load from DB: {e}")
    
    def save_to_db(self):
        try:
            session = get_session()
            for info_set in self.regret_sum:
                entry = session.query(RegretTable).filter_by(info_set=info_set).first()
                if entry:
                    entry.regrets = self.regret_sum[info_set].tolist()
                    entry.strategy_sum = self.strategy_sum[info_set].tolist()
                else:
                    entry = RegretTable(
                        info_set=info_set,
                        actions=self.ACTIONS,
                        regrets=self.regret_sum[info_set].tolist(),
                        strategy_sum=self.strategy_sum[info_set].tolist()
                    )
                    session.add(entry)
            session.commit()
            session.close()
        except Exception as e:
            print(f"Could not save to DB: {e}")
    
    def get_strategy(self, info_set: str) -> np.ndarray:
        if info_set not in self.regret_sum:
            self.regret_sum[info_set] = np.zeros(self.num_actions)
            self.strategy_sum[info_set] = np.zeros(self.num_actions)
        
        regrets = self.regret_sum[info_set]
        positive_regrets = np.maximum(regrets, 0)
        normalizing_sum = np.sum(positive_regrets)
        
        if normalizing_sum > 0:
            strategy = positive_regrets / normalizing_sum
        else:
            strategy = np.ones(self.num_actions) / self.num_actions
        
        return strategy
    
    def get_average_strategy(self, info_set: str) -> np.ndarray:
        if info_set not in self.strategy_sum:
            return np.ones(self.num_actions) / self.num_actions
        
        strategy_sum = self.strategy_sum[info_set]
        normalizing_sum = np.sum(strategy_sum)
        
        if normalizing_sum > 0:
            return strategy_sum / normalizing_sum
        else:
            return np.ones(self.num_actions) / self.num_actions
    
    def update_regrets(self, info_set: str, action_values: np.ndarray, 
                       actual_value: float):
        if info_set not in self.regret_sum:
            self.regret_sum[info_set] = np.zeros(self.num_actions)
            self.strategy_sum[info_set] = np.zeros(self.num_actions)
        
        regrets = action_values - actual_value
        self.regret_sum[info_set] += regrets
        
        strategy = self.get_strategy(info_set)
        self.strategy_sum[info_set] += strategy
    
    def get_action(self, info_set: str, available_actions: List[str] = None) -> Tuple[str, float]:
        strategy = self.get_average_strategy(info_set)
        
        if available_actions:
            action_mask = np.zeros(self.num_actions)
            for i, action in enumerate(self.ACTIONS):
                if action in available_actions:
                    action_mask[i] = 1
            
            masked_strategy = strategy * action_mask
            normalizing_sum = np.sum(masked_strategy)
            if normalizing_sum > 0:
                masked_strategy /= normalizing_sum
            else:
                masked_strategy = action_mask / np.sum(action_mask)
            
            action_index = np.random.choice(self.num_actions, p=masked_strategy)
        else:
            action_index = np.random.choice(self.num_actions, p=strategy)
        
        return self.ACTIONS[action_index], strategy[action_index]
    
    def calculate_ev(self, info_set: str, pot_size: float, 
                    current_bet: float, player_chips: float) -> Dict:
        strategy = self.get_average_strategy(info_set)
        
        fold_ev = 0
        
        check_call_ev = pot_size * 0.5 - current_bet
        
        raise_small_ev = pot_size * 0.55 - current_bet - pot_size * 0.5
        
        raise_big_ev = pot_size * 0.6 - current_bet - pot_size
        
        all_in_ev = pot_size * 0.65 - player_chips
        
        action_evs = {
            'fold': fold_ev,
            'check': check_call_ev,
            'call': check_call_ev,
            'raise_small': raise_small_ev,
            'raise_big': raise_big_ev,
            'all_in': all_in_ev
        }
        
        weighted_ev = sum(strategy[i] * ev for i, ev in enumerate(action_evs.values()))
        
        return {
            'action_evs': action_evs,
            'strategy': {self.ACTIONS[i]: float(strategy[i]) for i in range(self.num_actions)},
            'weighted_ev': float(weighted_ev),
            'recommended_action': max(action_evs, key=action_evs.get),
            'confidence': float(max(strategy))
        }
    
    def train(self, iterations: int = 1000):
        print(f"Training CFR Agent for {iterations} iterations...")
        
        for i in range(iterations):
            self._cfr_iteration()
            
            if (i + 1) % 100 == 0:
                print(f"Completed {i + 1} iterations")
        
        self.save_to_db()
        print("Training complete, saved to database")
    
    def _cfr_iteration(self):
        stages = ['preflop', 'flop', 'turn', 'river']
        hand_strengths = ['weak', 'medium', 'strong', 'premium']
        betting_histories = ['', 'c', 'r', 'cr', 'rr']
        pot_sizes = [20, 50, 100, 200]
        
        for stage in stages:
            for strength in hand_strengths:
                for history in betting_histories:
                    for pot in pot_sizes:
                        info_set = f"{strength}|{stage}|{history}|{pot}"
                        
                        strategy = self.get_strategy(info_set)
                        
                        strength_value = {'weak': 0.2, 'medium': 0.4, 
                                         'strong': 0.6, 'premium': 0.8}[strength]
                        
                        action_values = np.array([
                            0,
                            pot * (strength_value - 0.5) * 0.3,
                            pot * (strength_value - 0.5) * 0.5,
                            pot * (strength_value - 0.4) * 0.7 if strength_value > 0.4 else -pot * 0.3,
                            pot * (strength_value - 0.3) * 1.0 if strength_value > 0.5 else -pot * 0.5,
                            pot * (strength_value - 0.2) * 1.5 if strength_value > 0.6 else -pot * 1.0
                        ])
                        
                        actual_value = np.dot(strategy, action_values)
                        
                        self.update_regrets(info_set, action_values, actual_value)


def get_hand_strength_category(hole_cards: List, community_cards: List) -> str:
    total_cards = len(hole_cards) + len(community_cards)
    
    if total_cards < 4:
        high_ranks = ['A', 'K', 'Q', 'J', 'T']
        ranks = [c.rank if hasattr(c, 'rank') else c['rank'] for c in hole_cards]
        if all(r in high_ranks for r in ranks):
            if ranks[0] == ranks[1]:
                return 'premium'
            return 'strong'
        elif any(r in high_ranks for r in ranks):
            return 'medium'
        return 'weak'
    
    return 'medium'


def create_info_set(hole_cards: List, community_cards: List, 
                    betting_history: str, pot_size: float, stage: str) -> str:
    strength = get_hand_strength_category(hole_cards, community_cards)
    simplified_pot = int(pot_size // 25) * 25
    return f"{strength}|{stage}|{betting_history}|{simplified_pot}"
