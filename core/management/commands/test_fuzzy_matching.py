from django.core.management.base import BaseCommand
from core.fuzzy_matching import fuzzy_matcher


class Command(BaseCommand):
    help = 'Test fuzzy matching with nickname support'

    def add_arguments(self, parser):
        parser.add_argument('--name1', type=str, help='First name to compare')
        parser.add_argument('--name2', type=str, help='Second name to compare')

    def handle(self, *args, **options):
        name1 = options.get('name1', 'John Smith')
        name2 = options.get('name2', 'Johnny')
        
        self.stdout.write(f"Testing fuzzy matching between '{name1}' and '{name2}'")
        
        # Test similarity calculation
        similarity = fuzzy_matcher.calculate_similarity(name1, name2)
        self.stdout.write(f"Similarity score: {similarity:.2f}")
        
        # Test nickname matching
        is_nickname_match, nickname_confidence = fuzzy_matcher.check_nickname_match(name1, name2)
        self.stdout.write(f"Nickname match: {is_nickname_match}")
        self.stdout.write(f"Nickname confidence: {nickname_confidence:.2f}")
        
        # Test confidence level
        confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
        self.stdout.write(f"Confidence level: {confidence_level}")
        
        # Show loaded nickname mappings
        self.stdout.write(f"\nLoaded nickname mappings: {len(fuzzy_matcher.nickname_mappings)} entries")
        for full_name, nicknames in list(fuzzy_matcher.nickname_mappings.items())[:3]:
            self.stdout.write(f"  {full_name}: {nicknames}")
        
        # Test some example matches
        test_cases = [
            ("John Smith", "Johnny"),
            ("Michael Brown", "Mike"),
            ("Maria Garcia", "Mari"),
            ("Robert Anderson", "Rob"),
            ("Jennifer Martinez", "Jen"),
            ("John Smith", "Jane Smith"),  # Should not match
        ]
        
        self.stdout.write("\nTesting example cases:")
        for test_name1, test_name2 in test_cases:
            test_similarity = fuzzy_matcher.calculate_similarity(test_name1, test_name2)
            test_nickname_match, test_nickname_conf = fuzzy_matcher.check_nickname_match(test_name1, test_name2)
            final_similarity = max(test_similarity, test_nickname_conf)
            
            self.stdout.write(f"  '{test_name1}' vs '{test_name2}': {final_similarity:.2f} "
                            f"({'nickname' if test_nickname_match else 'similarity'})")
