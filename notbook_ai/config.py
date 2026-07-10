import yaml
import os
from dataclasses import dataclass

@dataclass
class Config:
    telegram_token: str
    gemini_api_key: str
    pinecone_api_key: str
    raw_config: dict

def load_config() -> Config:
    with open("config.yaml", "r") as f:
        yaml_data = yaml.safe_load(f)
    
    return Config(
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
        raw_config=yaml_data
    )

config = load_config()
