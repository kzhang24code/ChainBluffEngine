from sqlalchemy import create_engine, Column, Integer, String, JSON, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class RegretTable(Base):
    __tablename__ = 'regret_table'
    
    id = Column(Integer, primary_key=True)
    info_set = Column(String(512), unique=True, index=True)
    actions = Column(JSON)
    regrets = Column(JSON)
    strategy_sum = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GameState(Base):
    __tablename__ = 'game_states'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), index=True)
    pot = Column(Float, default=0.0)
    current_bet = Column(Float, default=0.0)
    stage = Column(String(20), default='preflop')
    community_cards = Column(JSON, default=list)
    players = Column(JSON, default=list)
    deck_seed_hash = Column(String(128))
    server_seed = Column(String(128))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HandHistory(Base):
    __tablename__ = 'hand_history'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), index=True)
    hand_number = Column(Integer)
    player_cards = Column(JSON)
    community_cards = Column(JSON)
    actions = Column(JSON)
    winner = Column(String(64))
    pot_won = Column(Float)
    hand_rank = Column(String(64))
    server_seed = Column(String(128))
    client_seed = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)


def get_engine():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chainbluff.db')
    return create_engine(f'sqlite:///{db_path}', echo=False)


def get_session():
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine
