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


class GameNode:
    def __init__(self, pot: float, player_to_act: int, betting_history: str,
                 hand_strength: float, stage: str, is_terminal: bool = False):
        self.pot = pot
        self.player_to_act = player_to_act
        self.betting_history = betting_history
        self.hand_strength = hand_strength
        self.stage = stage
        self.is_terminal = is_terminal
        self.terminal_value = 0.0


class CFRAgent:
    ACTIONS = ['fold', 'check', 'call', 'raise_half', 'raise_pot', 'all_in']
    NUM_ACTIONS = 6
    
    def __init__(self, load_from_db: bool = True):
        self.regret_sum: Dict[str, np.ndarray] = {}
        self.strategy_sum: Dict[str, np.ndarray] = {}
        self.iterations_run = 0
        
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
            self.regret_sum[info_set] = np.zeros(self.NUM_ACTIONS)
            self.strategy_sum[info_set] = np.zeros(self.NUM_ACTIONS)
        
        regrets = self.regret_sum[info_set]
        positive_regrets = np.maximum(regrets, 0)
        normalizing_sum = np.sum(positive_regrets)
        
        if normalizing_sum > 0:
            strategy = positive_regrets / normalizing_sum
        else:
            strategy = np.ones(self.NUM_ACTIONS) / self.NUM_ACTIONS
        
        return strategy
    
    def get_average_strategy(self, info_set: str) -> np.ndarray:
        if info_set not in self.strategy_sum:
            return np.ones(self.NUM_ACTIONS) / self.NUM_ACTIONS
        
        strategy_sum = self.strategy_sum[info_set]
        normalizing_sum = np.sum(strategy_sum)
        
        if normalizing_sum > 0:
            return strategy_sum / normalizing_sum
        else:
            return np.ones(self.NUM_ACTIONS) / self.NUM_ACTIONS
    
    def get_action(self, info_set: str, available_actions: List[str] = None) -> Tuple[str, float]:
        strategy = self.get_average_strategy(info_set)
        
        if available_actions:
            action_mask = np.zeros(self.NUM_ACTIONS)
            for i, action in enumerate(self.ACTIONS):
                base_action = action.replace('_half', '_small').replace('_pot', '_big')
                if action in available_actions or base_action in available_actions:
                    action_mask[i] = 1
                if action == 'check' and 'check' in available_actions:
                    action_mask[i] = 1
                if action == 'call' and 'call' in available_actions:
                    action_mask[i] = 1
                if action == 'fold' and 'fold' in available_actions:
                    action_mask[i] = 1
                if 'raise' in action and any('raise' in a for a in available_actions):
                    action_mask[i] = 1
            
            if np.sum(action_mask) == 0:
                action_mask = np.ones(self.NUM_ACTIONS)
            
            masked_strategy = strategy * action_mask
            normalizing_sum = np.sum(masked_strategy)
            if normalizing_sum > 0:
                masked_strategy /= normalizing_sum
            else:
                masked_strategy = action_mask / np.sum(action_mask)
            
            action_index = np.random.choice(self.NUM_ACTIONS, p=masked_strategy)
        else:
            action_index = np.random.choice(self.NUM_ACTIONS, p=strategy)
        
        return self.ACTIONS[action_index], float(strategy[action_index])
    
    def calculate_ev(self, info_set: str, pot_size: float, 
                    current_bet: float, player_chips: float,
                    hand_strength: float = 0.5) -> Dict:
        strategy = self.get_average_strategy(info_set)
        
        equity = hand_strength
        
        fold_ev = 0.0
        check_call_ev = pot_size * equity - current_bet * (1 - equity)
        raise_half_ev = (pot_size + pot_size * 0.5) * (equity * 1.1) - (current_bet + pot_size * 0.5) * (1 - equity)
        raise_pot_ev = (pot_size * 2) * (equity * 1.2) - (current_bet + pot_size) * (1 - equity * 1.1)
        all_in_ev = (pot_size + player_chips * 2) * (equity * 1.3) - player_chips * (1 - equity)
        
        if equity < 0.3:
            raise_half_ev *= 0.3
            raise_pot_ev *= 0.2
            all_in_ev *= 0.1
        
        action_evs = {
            'fold': fold_ev,
            'check': check_call_ev,
            'call': check_call_ev,
            'raise_half': raise_half_ev,
            'raise_pot': raise_pot_ev,
            'all_in': all_in_ev
        }
        
        weighted_ev = sum(strategy[i] * list(action_evs.values())[i] 
                         for i in range(self.NUM_ACTIONS))
        
        best_action = max(action_evs, key=action_evs.get)
        
        return {
            'action_evs': action_evs,
            'strategy': {self.ACTIONS[i]: float(strategy[i]) for i in range(self.NUM_ACTIONS)},
            'weighted_ev': float(weighted_ev),
            'recommended_action': best_action,
            'confidence': float(max(strategy)),
            'equity': equity
        }
    
    def train(self, iterations: int = 1000):
        print(f"Training CFR Agent for {iterations} iterations...")
        
        for i in range(iterations):
            p1_strength = np.random.random()
            p2_strength = np.random.random()
            
            initial_pot = 30.0
            self._cfr_traverse(
                pot=initial_pot,
                betting_history='',
                p1_strength=p1_strength,
                p2_strength=p2_strength,
                player_to_act=0,
                stage='preflop',
                reach_p1=1.0,
                reach_p2=1.0
            )
            
            self.iterations_run += 1
            
            if (i + 1) % 100 == 0:
                print(f"Completed {i + 1} iterations")
        
        self.save_to_db()
        print("Training complete, saved to database")
    
    def _cfr_traverse(self, pot: float, betting_history: str,
                      p1_strength: float, p2_strength: float,
                      player_to_act: int, stage: str,
                      reach_p1: float, reach_p2: float,
                      depth: int = 0) -> float:
        if depth > 10 or len(betting_history) > 8:
            winner = 1 if p1_strength > p2_strength else -1
            return pot * 0.5 * winner
        
        if 'f' in betting_history:
            if betting_history.endswith('f'):
                return pot * 0.5 if player_to_act == 1 else -pot * 0.5
        
        if betting_history.count('c') >= 2 or betting_history.endswith('cc'):
            winner = 1 if p1_strength > p2_strength else -1
            return pot * 0.5 * winner
        
        strength = p1_strength if player_to_act == 0 else p2_strength
        strength_cat = self._categorize_strength(strength)
        info_set = f"{strength_cat}|{stage}|{betting_history}|{int(pot)}"
        
        strategy = self.get_strategy(info_set)
        action_values = np.zeros(self.NUM_ACTIONS)
        
        for a_idx, action in enumerate(self.ACTIONS):
            new_pot = pot
            new_history = betting_history
            
            if action == 'fold':
                action_values[a_idx] = -pot * 0.5 if player_to_act == 0 else pot * 0.5
                continue
            elif action == 'check' or action == 'call':
                new_history += 'c'
            elif action == 'raise_half':
                new_pot += pot * 0.5
                new_history += 'r'
            elif action == 'raise_pot':
                new_pot += pot
                new_history += 'R'
            elif action == 'all_in':
                new_pot += pot * 2
                new_history += 'A'
            
            next_player = 1 - player_to_act
            if player_to_act == 0:
                action_values[a_idx] = -self._cfr_traverse(
                    new_pot, new_history, p1_strength, p2_strength,
                    next_player, stage, reach_p1 * strategy[a_idx], reach_p2,
                    depth + 1
                )
            else:
                action_values[a_idx] = -self._cfr_traverse(
                    new_pot, new_history, p1_strength, p2_strength,
                    next_player, stage, reach_p1, reach_p2 * strategy[a_idx],
                    depth + 1
                )
        
        counterfactual_value = np.dot(strategy, action_values)
        
        regrets = action_values - counterfactual_value
        
        if info_set not in self.regret_sum:
            self.regret_sum[info_set] = np.zeros(self.NUM_ACTIONS)
            self.strategy_sum[info_set] = np.zeros(self.NUM_ACTIONS)
        
        opponent_reach = reach_p2 if player_to_act == 0 else reach_p1
        self.regret_sum[info_set] += opponent_reach * regrets
        
        player_reach = reach_p1 if player_to_act == 0 else reach_p2
        self.strategy_sum[info_set] += player_reach * strategy
        
        return counterfactual_value
    
    def _categorize_strength(self, strength: float) -> str:
        if strength < 0.25:
            return 'weak'
        elif strength < 0.5:
            return 'medium'
        elif strength < 0.75:
            return 'strong'
        else:
            return 'premium'


def get_hand_strength_category(hole_cards: List, community_cards: List) -> str:
    total_cards = len(hole_cards) + len(community_cards)
    
    if total_cards < 4:
        high_ranks = ['A', 'K', 'Q', 'J', 'T']
        ranks = [c.rank if hasattr(c, 'rank') else c['rank'] for c in hole_cards]
        if all(r in high_ranks for r in ranks):
            if len(set(ranks)) == 1:
                return 'premium'
            return 'strong'
        elif any(r in high_ranks for r in ranks):
            return 'medium'
        return 'weak'
    
    return 'medium'


def estimate_hand_equity(hole_cards: List, community_cards: List, stage: str) -> float:
    high_ranks = ['A', 'K', 'Q', 'J', 'T']
    ranks = [c.rank if hasattr(c, 'rank') else c.get('rank', '2') for c in hole_cards]
    
    base_equity = 0.3
    
    for rank in ranks:
        if rank == 'A':
            base_equity += 0.15
        elif rank == 'K':
            base_equity += 0.12
        elif rank == 'Q':
            base_equity += 0.10
        elif rank == 'J':
            base_equity += 0.08
        elif rank == 'T':
            base_equity += 0.06
        else:
            base_equity += 0.02
    
    if len(set(ranks)) == 1:
        base_equity += 0.15
    
    suits = [c.suit if hasattr(c, 'suit') else c.get('suit', 'x') for c in hole_cards]
    if len(set(suits)) == 1:
        base_equity += 0.05
    
    return min(0.95, max(0.05, base_equity))


def create_info_set(hole_cards: List, community_cards: List, 
                    betting_history: str, pot_size: float, stage: str) -> str:
    strength = get_hand_strength_category(hole_cards, community_cards)
    simplified_pot = int(pot_size // 25) * 25
    simplified_pot = max(20, min(simplified_pot, 200))
    return f"{strength}|{stage}|{betting_history}|{simplified_pot}"
