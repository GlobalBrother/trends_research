import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

from src.api.routers import auth, admin, niche, trends, clusters, ads, my_brands, monitoring

print("Successfully imported all routers.")
