import json
import os
from difflib import SequenceMatcher
from typing import List, Tuple, Optional, Dict, Any
from django.conf import settings


class FuzzyMatcher:
    """Fuzzy matching utility for client names with nickname support"""
    
    def __init__(self):
        self.nickname_mappings = self._load_nickname_mappings()
    
    def _load_nickname_mappings(self) -> Dict[str, List[str]]:
        """Load nickname mappings from JSON file or use default mappings"""
        # Try to load from a JSON file first
        nickname_file = getattr(settings, 'NICKNAME_MAPPINGS_FILE', None)
        if nickname_file and os.path.exists(nickname_file):
            try:
                with open(nickname_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Default nickname mappings
        return {
            "Rohit Singh": ["Rohit", "RS", "Singh", "R. Singh"],
            "Hemo Globin": ["HG", "Hemo", "Hobo", "Globin"],
            "John Smith": ["JS", "Johnny", "John", "Smith", "Jon"],
            "Maria Garcia": ["MG", "Maria", "Garcia", "Mari"],
            "Sarah Williams": ["SW", "Sarah", "Williams", "Sally"],
            "Michael Brown": ["MB", "Mike", "Mikey", "Michael", "Brown"],
            "Lisa Davis": ["LD", "Lisa", "Liz", "Liza", "Davis"],
            "James Wilson": ["JW", "Jim", "Jimmy", "James", "Wilson"],
            "Jennifer Martinez": ["JM", "Jen", "Jenny", "Martinez"],
            "Robert Anderson": ["RA", "Rob", "Bobby", "Robert", "Anderson", "Robbie"]
        }
    
    def normalize_name(self, name: str) -> str:
        """Normalize name for comparison"""
        if not name:
            return ""
        return " ".join(name.lower().strip().split())
    
    def calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names (0-1 scale)"""
        if not name1 or not name2:
            return 0.0
        
        name1_norm = self.normalize_name(name1)
        name2_norm = self.normalize_name(name2)
        
        if name1_norm == name2_norm:
            return 1.0
        
        # Check if one name contains the other
        if name1_norm in name2_norm or name2_norm in name1_norm:
            return 0.8
        
        # Use SequenceMatcher for more accurate similarity
        similarity = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        
        # Check for common words
        words1 = set(name1_norm.split())
        words2 = set(name2_norm.split())
        if words1 and words2:
            common_words = len(words1.intersection(words2))
            total_words = len(words1.union(words2))
            word_similarity = common_words / total_words if total_words > 0 else 0
            # Take the higher of the two similarities
            similarity = max(similarity, word_similarity)
        
        return similarity
    
    def check_nickname_match(self, name1: str, name2: str) -> Tuple[bool, float]:
        """Check if two names match through nickname mappings"""
        name1_norm = self.normalize_name(name1)
        name2_norm = self.normalize_name(name2)
        
        # Check direct nickname mappings
        for full_name, nicknames in self.nickname_mappings.items():
            full_name_norm = self.normalize_name(full_name)
            
            # Check if name1 matches full name and name2 matches a nickname
            if name1_norm == full_name_norm:
                for nickname in nicknames:
                    if self.normalize_name(nickname) == name2_norm:
                        return True, 0.9  # High confidence for nickname match
            
            # Check if name2 matches full name and name1 matches a nickname
            if name2_norm == full_name_norm:
                for nickname in nicknames:
                    if self.normalize_name(nickname) == name1_norm:
                        return True, 0.9  # High confidence for nickname match
            
            # Check if both names are nicknames of the same full name
            name1_is_nickname = any(self.normalize_name(nickname) == name1_norm for nickname in nicknames)
            name2_is_nickname = any(self.normalize_name(nickname) == name2_norm for nickname in nicknames)
            
            if name1_is_nickname and name2_is_nickname:
                return True, 0.85  # High confidence for both being nicknames
        
        return False, 0.0
    
    def find_potential_duplicates(self, client_data: Dict[str, Any], existing_clients: List[Any], 
                                similarity_threshold: float = 0.7) -> List[Tuple[Any, str, float]]:
        """Find potential duplicate clients based on name similarity and nickname matching"""
        potential_duplicates = []
        client_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
        
        if not client_name:
            return potential_duplicates
        
        for existing_client in existing_clients:
            existing_name = f"{existing_client.first_name} {existing_client.last_name}".strip()
            
            # Calculate basic similarity
            similarity = self.calculate_similarity(client_name, existing_name)
            
            # Check for nickname match
            is_nickname_match, nickname_confidence = self.check_nickname_match(client_name, existing_name)
            
            # Use the higher confidence score
            final_similarity = max(similarity, nickname_confidence)
            
            if final_similarity >= similarity_threshold:
                match_type = "nickname" if is_nickname_match else "similarity"
                potential_duplicates.append((existing_client, match_type, final_similarity))
        
        # Sort by similarity score (highest first)
        potential_duplicates.sort(key=lambda x: x[2], reverse=True)
        
        return potential_duplicates
    
    def get_duplicate_confidence_level(self, similarity: float) -> str:
        """Get confidence level based on similarity score"""
        if similarity >= 0.9:
            return "high"
        elif similarity >= 0.7:
            return "medium"
        elif similarity >= 0.5:
            return "low"
        else:
            return "very_low"
    
    def should_create_duplicate_warning(self, client_data: Dict[str, Any], existing_clients: List[Any]) -> bool:
        """Determine if a duplicate warning should be created for a new client"""
        # Only create warnings if there's no email or phone (unique identifiers)
        has_email = bool(client_data.get('email', '').strip())
        has_phone = bool(client_data.get('phone', '').strip())
        
        if has_email or has_phone:
            return False
        
        # Check for potential duplicates
        potential_duplicates = self.find_potential_duplicates(client_data, existing_clients)
        
        # Create warning if there are medium or high confidence matches
        return any(conf >= 0.7 for _, _, conf in potential_duplicates)


# Global instance
fuzzy_matcher = FuzzyMatcher()
