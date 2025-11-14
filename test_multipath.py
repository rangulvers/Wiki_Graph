"""
Quick test script for multi-path functionality
"""
import asyncio
from app import WikipediaPathFinder

async def test_multipath():
    """Test multi-path finding between two Wikipedia pages"""
    print("Testing multi-path finder...")
    print("=" * 60)

    async with WikipediaPathFinder(max_depth=4) as finder:
        # Test with pages that should have multiple paths
        start = "Python (programming language)"
        end = "Computer science"

        print(f"\nSearching for multiple paths:")
        print(f"  Start: {start}")
        print(f"  End: {end}")
        print(f"  Max paths: 3")
        print(f"  Min diversity: 0.3")
        print()

        paths = await finder.find_k_paths_bidirectional(
            start,
            end,
            max_paths=3,
            min_diversity=0.3,
            callback=lambda event_type, data: print(f"  [{event_type}] {data}")
        )

        if paths:
            print(f"\n✓ Found {len(paths)} paths!\n")
            for i, path in enumerate(paths, 1):
                print(f"Path {i} ({len(path)-1} hops):")
                print(f"  {' → '.join(path)}")
                print()
        else:
            print("\n✗ No paths found")

if __name__ == "__main__":
    asyncio.run(test_multipath())
