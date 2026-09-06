from __future__ import annotations
import threading,time,logging
log=logging.getLogger(__name__)

class ProactiveScheduler:
    """Tiny wake-up loop; timing decisions live in persistent chat state."""
    def __init__(self,callback): self.callback=callback; self._stop=threading.Event(); self._thread=None
    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread=threading.Thread(target=self._run,daemon=True,name="almirfawya-proactive"); self._thread.start()
    def stop(self): self._stop.set()
    def _run(self):
        while not self._stop.wait(30):
            try: self.callback()
            except Exception: log.exception("proactive scheduler failure")
