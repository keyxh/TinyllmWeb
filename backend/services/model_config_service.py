import json
import os
from typing import List, Dict, Optional


class ModelConfigService:
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), 'models_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)
    
    def get_all_models(self) -> List[Dict]:
        return self._config.get('models', [])
    
    def get_enabled_models(self) -> List[Dict]:
        return [m for m in self._config.get('models', []) if m.get('enable', True)]
    
    def get_model_by_name(self, name: str) -> Optional[Dict]:
        for model in self._config.get('models', []):
            if model['name'] == name:
                return model
        return None
    
    def get_model_training_cost(self, name: str) -> Optional[Dict]:
        model = self.get_model_by_name(name)
        if model:
            return model.get('training_cost')
        return None
    
    def get_model_deploy_cost(self, name: str) -> Optional[Dict]:
        model = self.get_model_by_name(name)
        if model:
            return model.get('deploy_cost_per_day')
        return None
    
    def is_model_enabled(self, name: str) -> bool:
        model = self.get_model_by_name(name)
        if model:
            return model.get('enable', True)
        return False


model_config_service = ModelConfigService()
