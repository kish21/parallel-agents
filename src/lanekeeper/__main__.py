"""`python -m lanekeeper`: the same program as the `lanekeeper` shim.

The module form exists for the install where the shim is not on PATH — Windows Store
Python is the common case — and until this file existed it had to be spelled
`python -m lanekeeper.cli`. A fallback that is typed by people who have just hit a
wall should be as short as it can be.
"""

from .cli import main

if __name__ == "__main__":
    main()
