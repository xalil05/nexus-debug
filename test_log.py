import logging, sys

# Configure logging
logging.basicConfig(level=logging.INFO, force=True, stream=sys.stdout)
log = logging.getLogger("test")

log.info("STDOUT log test")

# File handler
fh = logging.FileHandler("/tmp/test.log")
fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
log.addHandler(fh)
log.info("FILE log test")

print("PRINT test - done", flush=True)
