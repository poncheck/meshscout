# Fix for h3 Module Error on Remote System

## Problem
The remote mesh-scout system has an error where:
1. The `h3` Python module is missing
2. `logger` is used before it's defined in an exception handler

## Solution

### Option 1: Install the h3 module (Recommended)

SSH into your remote system and run:

```bash
cd ~/mesh-scout
pip3 install h3
# or if using a virtual environment:
# source venv/bin/activate
# pip install h3
```

Then restart the application:
```bash
./run.sh --config config.json
```

### Option 2: Make h3 optional (if you don't need H3 features)

If you don't need H3 geospatial features, you need to fix the database.py file on the remote system to define logger before the try/except block.

On your remote system, edit `database.py`:

1. Make sure `logger = logging.getLogger(__name__)` appears on line 14 (BEFORE any try/except blocks)
2. The try/except block for h3_utils import should come AFTER the logger definition

The correct order should be:
```python
import logging
# ... other imports ...

logger = logging.getLogger(__name__)  # <-- Must be defined first

# Then the try/except block:
try:
    from h3_utils import lat_lon_to_h3, DEFAULT_H3_RESOLUTION
    H3_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    logger.warning("H3 utilities not available - H3 features disabled")
    H3_AVAILABLE = False
```

## Recommended: Add h3 to requirements.txt

Add this line to your requirements.txt on the remote system:
```
h3>=3.7.0
```

Then install all requirements:
```bash
pip3 install -r requirements.txt
```

## Quick Fix Command

Run this on your remote system:
```bash
cd ~/mesh-scout
pip3 install h3
