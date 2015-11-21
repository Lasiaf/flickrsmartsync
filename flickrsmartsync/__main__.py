import os
import sys

__author__ = 'faisal'


if __name__ == "__main__":
    # Access from source
    root_path = os.path.abspath(__file__).split(os.sep)[:-2]
    sys.path.insert(0, os.sep.join(root_path))
    import flickrsmartsync
    flickrsmartsync.main()
