import os
import json
import hashlib
from typing import Optional, Dict
from web3 import Web3
from eth_account import Account


POKER_POT_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [{"name": "gameId", "type": "bytes32"}],
        "name": "createGame",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "gameId", "type": "bytes32"},
            {"name": "commitment", "type": "bytes32"}
        ],
        "name": "commitHand",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "gameId", "type": "bytes32"},
            {"name": "winner", "type": "address"},
            {"name": "serverSeed", "type": "bytes32"},
            {"name": "clientSeed", "type": "bytes32"}
        ],
        "name": "revealAndPayout",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"name": "gameId", "type": "bytes32"}],
        "name": "getGamePot",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "gameId", "type": "bytes32"}],
        "name": "getGameState",
        "outputs": [
            {"name": "pot", "type": "uint256"},
            {"name": "isActive", "type": "bool"},
            {"name": "commitment", "type": "bytes32"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "gameId", "type": "bytes32"},
            {"indexed": False, "name": "pot", "type": "uint256"}
        ],
        "name": "GameCreated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "gameId", "type": "bytes32"},
            {"indexed": True, "name": "winner", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"}
        ],
        "name": "GameResolved",
        "type": "event"
    }
]

POKER_POT_BYTECODE = "0x608060405234801561001057600080fd5b50336000806101000a81548173ffffffffffffffffffffffffffffffffffffffff021916908373ffffffffffffffffffffffffffffffffffffffff160217905550610a3a806100606000396000f3fe"


class BlockchainBridge:
    def __init__(self, provider_url: Optional[str] = None, 
                 private_key: Optional[str] = None,
                 contract_address: Optional[str] = None):
        self.provider_url = provider_url or os.getenv('ETH_PROVIDER_URL', 'http://localhost:8545')
        self.private_key = private_key or os.getenv('ETH_PRIVATE_KEY')
        self.contract_address = contract_address or os.getenv('POKER_CONTRACT_ADDRESS')
        
        self.w3 = None
        self.account = None
        self.contract = None
        self.connected = False
        
        self._connect()
    
    def _connect(self):
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.provider_url))
            
            if self.w3.is_connected():
                self.connected = True
                
                if self.private_key:
                    self.account = Account.from_key(self.private_key)
                
                if self.contract_address:
                    self.contract = self.w3.eth.contract(
                        address=self.contract_address,
                        abi=POKER_POT_ABI
                    )
            else:
                print("Warning: Could not connect to Ethereum node")
                self.connected = False
        except Exception as e:
            print(f"Blockchain connection error: {e}")
            self.connected = False
    
    def is_connected(self) -> bool:
        return self.connected and self.w3 is not None and self.w3.is_connected()
    
    def deploy_contract(self) -> Optional[str]:
        if not self.is_connected() or not self.account:
            return None
        
        try:
            contract = self.w3.eth.contract(abi=POKER_POT_ABI, bytecode=POKER_POT_BYTECODE)
            
            tx = contract.constructor().build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 2000000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            self.contract_address = receipt.contractAddress
            self.contract = self.w3.eth.contract(
                address=self.contract_address,
                abi=POKER_POT_ABI
            )
            
            return self.contract_address
        except Exception as e:
            print(f"Contract deployment error: {e}")
            return None
    
    def create_game(self, game_id: str, initial_pot_wei: int) -> Optional[str]:
        if not self.is_connected() or not self.contract:
            return None
        
        try:
            game_id_bytes = self._string_to_bytes32(game_id)
            
            tx = self.contract.functions.createGame(game_id_bytes).build_transaction({
                'from': self.account.address,
                'value': initial_pot_wei,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            return tx_hash.hex()
        except Exception as e:
            print(f"Create game error: {e}")
            return None
    
    def commit_hand(self, game_id: str, commitment: str) -> Optional[str]:
        if not self.is_connected() or not self.contract:
            return None
        
        try:
            game_id_bytes = self._string_to_bytes32(game_id)
            commitment_bytes = self._string_to_bytes32(commitment)
            
            tx = self.contract.functions.commitHand(
                game_id_bytes, commitment_bytes
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            return tx_hash.hex()
        except Exception as e:
            print(f"Commit hand error: {e}")
            return None
    
    def reveal_and_payout(self, game_id: str, winner_address: str,
                          server_seed: str, client_seed: str) -> Optional[str]:
        if not self.is_connected() or not self.contract:
            return None
        
        try:
            game_id_bytes = self._string_to_bytes32(game_id)
            server_seed_bytes = self._string_to_bytes32(server_seed)
            client_seed_bytes = self._string_to_bytes32(client_seed)
            
            tx = self.contract.functions.revealAndPayout(
                game_id_bytes,
                Web3.to_checksum_address(winner_address),
                server_seed_bytes,
                client_seed_bytes
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': 150000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            return tx_hash.hex()
        except Exception as e:
            print(f"Reveal and payout error: {e}")
            return None
    
    def get_game_state(self, game_id: str) -> Optional[Dict]:
        if not self.is_connected() or not self.contract:
            return None
        
        try:
            game_id_bytes = self._string_to_bytes32(game_id)
            result = self.contract.functions.getGameState(game_id_bytes).call()
            
            return {
                'pot': result[0],
                'is_active': result[1],
                'commitment': result[2].hex()
            }
        except Exception as e:
            print(f"Get game state error: {e}")
            return None
    
    def get_balance(self, address: Optional[str] = None) -> Optional[int]:
        if not self.is_connected():
            return None
        
        try:
            addr = address or (self.account.address if self.account else None)
            if not addr:
                return None
            return self.w3.eth.get_balance(addr)
        except Exception as e:
            print(f"Get balance error: {e}")
            return None
    
    def _string_to_bytes32(self, s: str) -> bytes:
        if s.startswith('0x'):
            s = s[2:]
        if len(s) >= 64:
            return bytes.fromhex(s[:64])
        return hashlib.sha256(s.encode()).digest()
    
    def generate_commitment(self, server_seed: str) -> str:
        return hashlib.sha256(server_seed.encode()).hexdigest()
    
    def verify_commitment(self, server_seed: str, commitment: str) -> bool:
        expected = self.generate_commitment(server_seed)
        return expected == commitment


def get_bridge() -> BlockchainBridge:
    return BlockchainBridge()
