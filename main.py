#!/usr/bin/env python3

import sys
from launcher import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Unhandled exception: {e}")
        sys.exit(1)
