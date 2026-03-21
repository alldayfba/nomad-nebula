#!/usr/bin/env python3
"""Launch Nova Sales Discord bot."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from execution.discord_bot_sales.main import main

if __name__ == "__main__":
    asyncio.run(main())
