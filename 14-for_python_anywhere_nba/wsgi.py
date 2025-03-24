import sys
import os

# Add your project directory to the Python path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

from application import app as application

# For local development only
if __name__ == "__main__":
    application.run()
