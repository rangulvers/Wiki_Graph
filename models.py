from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re


class SearchRequest(BaseModel):
    """Request model for path finding"""
    start: str = Field(..., min_length=1, max_length=200, description="Starting Wikipedia page")
    end: str = Field(..., min_length=1, max_length=200, description="Target Wikipedia page")
    max_paths: int = Field(default=1, ge=1, le=5, description="Maximum number of paths to find (1-5)")
    min_diversity: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum diversity between paths (0-1)")

    @field_validator('start', 'end')
    @classmethod
    def validate_search_term(cls, v: str) -> str:
        """
        Validate and sanitize search terms:
        - Strip whitespace
        - Check length
        - Prevent malicious patterns (SQL injection attempts, XSS)
        - Allow alphanumeric, spaces, hyphens, parentheses, apostrophes
        """
        # Strip whitespace
        v = v.strip()

        # Check minimum length
        if len(v) < 1:
            raise ValueError("Search term cannot be empty")

        # Check maximum length
        if len(v) > 200:
            raise ValueError("Search term too long (max 200 characters)")

        # Prevent obvious malicious patterns
        malicious_patterns = [
            r'<script',
            r'javascript:',
            r'onerror=',
            r'onclick=',
            r'--',  # SQL comment
            r';.*DROP',
            r';.*DELETE',
            r';.*INSERT',
            r';.*UPDATE',
        ]

        v_lower = v.lower()
        for pattern in malicious_patterns:
            if re.search(pattern, v_lower, re.IGNORECASE):
                raise ValueError(f"Invalid characters detected in search term")

        # Allow reasonable Wikipedia title characters
        # Wikipedia titles can contain: letters, numbers, spaces, hyphens, parentheses, apostrophes, periods, commas, ampersands
        if not re.match(r'^[a-zA-Z0-9\s\-\(\)\'\.,&]+$', v):
            raise ValueError("Search term contains invalid characters. Use only letters, numbers, spaces, and common punctuation.")

        return v


class Node(BaseModel):
    """Graph node for visualization"""
    id: int
    label: str
    title: str


class Edge(BaseModel):
    """Graph edge for visualization"""
    from_: int = Field(..., alias="from")
    to: int

    class Config:
        populate_by_name = True


class PathInfo(BaseModel):
    """Information about a single path"""
    path: List[str]
    hops: int
    nodes: List[Node]
    edges: List[Edge]
    diversity_score: Optional[float] = None  # Diversity vs other paths (0-1)
    is_cached: bool = False
    cache_segments: List[str] = []  # Which segments came from cache


class SearchResponse(BaseModel):
    """Response model for successful path finding"""
    success: bool
    search_id: Optional[int] = None
    path: List[str]  # Keep for backwards compatibility (shortest path)
    paths: Optional[List[PathInfo]] = None  # Multiple paths if max_paths > 1
    nodes: List[Node]
    edges: List[Edge]
    hops: int
    pages_checked: int
    paths_found: Optional[int] = None  # Number of paths found


class SearchErrorResponse(BaseModel):
    """Response model for failed path finding"""
    success: bool = False
    search_id: Optional[int] = None
    error: str
    pages_checked: int


class SearchRecord(BaseModel):
    """Database search record"""
    id: int
    start_term: str
    end_term: str
    hops: int
    pages_checked: int
    success: int
    created_at: datetime


class SearchRecordDetail(SearchRecord):
    """Detailed search record with path"""
    path: Optional[List[str]] = None
    error_message: Optional[str] = None
    nodes: Optional[List[Node]] = None
    edges: Optional[List[Edge]] = None


class SearchListResponse(BaseModel):
    """Response model for list of searches"""
    searches: List[SearchRecord]


class SearchStats(BaseModel):
    """Search statistics"""
    total_searches: int
    successful_searches: int
    avg_hops: Optional[float] = None
    avg_pages_checked: Optional[float] = None
