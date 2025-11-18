"""
Utility functions for the application
"""

def normalize_title(title: str) -> str:
    """
    Normalize Wikipedia title for consistent cache keys

    Args:
        title: Wikipedia page title

    Returns:
        Normalized title (lowercase, spaces instead of underscores)
    """
    return title.strip().replace("_", " ").lower()
