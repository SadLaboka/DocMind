#!/usr/bin/env python3
"""Wrapper for running Alembic migrations with local host override"""

import os
import sys

from alembic.config import main as alembic_main

os.environ["ALEMBIC_FORCE_LOCAL_HOST"] = "true"

sys.exit(alembic_main())
