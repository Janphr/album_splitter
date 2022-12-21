import os
import sys

# Adds "album_splitter" to sys.path
# Now you can do import with "from album_splitter.Sub-Package ..."
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "album_splitter"))
)
