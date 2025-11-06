import logging
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

LOG_FILE = os.path.join(LOG_DIR, f"app.log")


logging.basicConfig(

   level=logging.INFO,
   format= '%(asctime)s [%(levelname)s] %(name)s : %(message)s',
   handlers=[
       logging.FileHandler(LOG_FILE, encoding="utf-8"),
       logging.StreamHandler()
   ]
)
logger = logging.getLogger("app.logger")
logging.getLogger("watchfiles").setLevel(logging.ERROR)